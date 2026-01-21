import os
import logging
from flask import Flask, request, jsonify
import stripe
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Environment variables
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
GHL_API_KEY = os.getenv('GHL_API_KEY')
GHL_LOCATION_ID = os.getenv('GHL_LOCATION_ID')

# GHL API v2 base URL
GHL_BASE_URL = 'https://services.leadconnectorhq.com'


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Railway."""
    return jsonify({'status': 'healthy'}), 200


@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Handle incoming Stripe webhook events."""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')

    # Verify webhook signature
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f'Invalid payload: {e}')
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        logger.error(f'Invalid signature: {e}')
        return jsonify({'error': 'Invalid signature'}), 400

    # Handle specific events
    event_type = event['type']
    logger.info(f'Received event: {event_type}')

    if event_type in ['checkout.session.completed', 'payment_intent.succeeded']:
        handle_payment_event(event)

    # Always return 200 to prevent Stripe retries
    return jsonify({'received': True}), 200


def handle_payment_event(event):
    """Process payment events and sync to GHL."""
    try:
        data = event['data']['object']

        # Extract customer email from various possible locations
        email = None

        # 1. checkout.session.completed: customer_details.email
        if 'customer_details' in data and data['customer_details']:
            email = data['customer_details'].get('email')

        # 2. payment_intent: receipt_email
        if not email:
            email = data.get('receipt_email')

        # 3. payment_intent: billing_details.email (direct)
        if not email and 'billing_details' in data and data['billing_details']:
            email = data['billing_details'].get('email')

        # 4. payment_intent: charges.data[0].billing_details.email
        if not email and 'charges' in data and data['charges'].get('data'):
            charges = data['charges']['data']
            if charges and charges[0].get('billing_details'):
                email = charges[0]['billing_details'].get('email')

        # 5. payment_intent: latest_charge.billing_details.email (if expanded)
        if not email and 'latest_charge' in data and isinstance(data['latest_charge'], dict):
            latest_charge = data['latest_charge']
            if latest_charge.get('billing_details'):
                email = latest_charge['billing_details'].get('email')

        if not email:
            logger.warning('No email found in payment event')
            logger.debug(f'Event data keys: {data.keys()}')
            return

        # Extract billing details from various sources
        billing_details = {}
        address = {}

        # Try billing_details first
        if data.get('billing_details'):
            billing_details = data['billing_details']
            address = billing_details.get('address', {}) or {}

        # Try charges array for payment_intent
        if not billing_details.get('name') and 'charges' in data and data['charges'].get('data'):
            charges = data['charges']['data']
            if charges and charges[0].get('billing_details'):
                billing_details = charges[0]['billing_details']
                address = billing_details.get('address', {}) or {}

        # Try customer_details for checkout.session
        if not billing_details.get('name') and 'customer_details' in data:
            customer_details = data.get('customer_details', {}) or {}
            billing_details['name'] = customer_details.get('name')
            if not address:
                address = customer_details.get('address', {}) or {}

        # Extract amount and convert from cents to dollars
        amount_cents = data.get('amount_total') or data.get('amount') or 0
        amount_dollars = f"{amount_cents / 100:.2f}"

        # Prepare data for GHL
        ghl_data = {
            'name': billing_details.get('name', ''),
            'address_line_1': address.get('line1', ''),
            'address_line_2': address.get('line2', ''),
            'city': address.get('city', ''),
            'state': address.get('state', ''),
            'country': address.get('country', ''),
            'amount': amount_dollars
        }

        logger.info(f'Processing payment for {email}: ${amount_dollars}')

        # Sync to GHL
        sync_to_ghl(email, ghl_data)

    except Exception as e:
        logger.error(f'Error processing payment event: {e}')


def sync_to_ghl(email, data):
    """Look up contact in GHL and update custom fields."""
    headers = {
        'Authorization': f'Bearer {GHL_API_KEY}',
        'Content-Type': 'application/json',
        'Version': '2021-07-28'
    }

    try:
        # Look up contact by email using v2 API
        lookup_url = f'{GHL_BASE_URL}/contacts/?locationId={GHL_LOCATION_ID}&query={email}'
        response = requests.get(lookup_url, headers=headers)

        if response.status_code != 200:
            logger.error(f'GHL lookup failed: {response.status_code} - {response.text}')
            return

        result = response.json()
        contacts = result.get('contacts', [])

        if not contacts:
            logger.warning(f'No contact found in GHL for email: {email}')
            return

        contact_id = contacts[0].get('id')

        # Prepare custom fields update payload (v2 format)
        update_payload = {
            'customFields': [
                {'key': 'card_name', 'field_value': data['name']},
                {'key': 'card_address_line_1', 'field_value': data['address_line_1']},
                {'key': 'card_address_line_2', 'field_value': data['address_line_2']},
                {'key': 'card_address_city', 'field_value': data['city']},
                {'key': 'card_address_state', 'field_value': data['state']},
                {'key': 'card_address_country', 'field_value': data['country']},
                {'key': 'total_spend', 'field_value': data['amount']}
            ]
        }

        # Update contact
        update_url = f'{GHL_BASE_URL}/contacts/{contact_id}'
        update_response = requests.put(update_url, headers=headers, json=update_payload)

        if update_response.status_code == 200:
            logger.info(f'Successfully updated GHL contact {contact_id} for {email}')
        else:
            logger.error(f'GHL update failed: {update_response.status_code} - {update_response.text}')

    except Exception as e:
        logger.error(f'Error syncing to GHL: {e}')


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
