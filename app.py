import os
import json
import logging
from flask import Flask, request, jsonify
import stripe
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging - use DEBUG level for verbose output
logging.basicConfig(
    level=logging.DEBUG,
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


def safe_json(obj, max_length=2000):
    """Safely convert object to JSON string for logging, truncating if needed."""
    try:
        result = json.dumps(obj, default=str, indent=2)
        if len(result) > max_length:
            return result[:max_length] + '... [truncated]'
        return result
    except Exception as e:
        return f'[Could not serialize: {e}]'


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Railway."""
    return jsonify({'status': 'healthy'}), 200


@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Handle incoming Stripe webhook events."""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')

    logger.info('=' * 60)
    logger.info('WEBHOOK RECEIVED')
    logger.info('=' * 60)

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

    # Log event details
    event_type = event['type']
    event_id = event.get('id', 'unknown')
    logger.info(f'Event ID: {event_id}')
    logger.info(f'Event Type: {event_type}')

    if event_type in ['checkout.session.completed', 'payment_intent.succeeded', 'charge.succeeded']:
        handle_payment_event(event)
    else:
        logger.info(f'Ignoring event type: {event_type}')

    # Always return 200 to prevent Stripe retries
    return jsonify({'received': True}), 200


def handle_payment_event(event):
    """Process payment events and sync to GHL."""
    try:
        event_type = event['type']
        data = event['data']['object']

        logger.info('-' * 40)
        logger.info('PROCESSING PAYMENT EVENT')
        logger.info('-' * 40)

        # Log all available top-level keys in the data object
        logger.info(f'Available data keys: {list(data.keys())}')

        # Log metadata - this often contains contactId from GHL
        metadata = data.get('metadata', {})
        logger.info(f'[Metadata] {safe_json(metadata)}')

        # Check for GHL contactId in metadata FIRST (most reliable method)
        contact_id = metadata.get('contactId')
        if contact_id:
            logger.info(f'[Contact] Found contactId in metadata: {contact_id}')
        else:
            logger.info('[Contact] No contactId in metadata')

        # Log key fields for debugging
        logger.debug(f'Full event data:\n{safe_json(data)}')

        # Extract customer email from various possible locations (as fallback)
        email = None
        email_source = None

        # 1. checkout.session.completed: customer_details.email
        if 'customer_details' in data and data['customer_details']:
            cd_email = data['customer_details'].get('email')
            logger.info(f'[Email Check 1] customer_details.email: {cd_email}')
            if cd_email and not email:
                email = cd_email
                email_source = 'customer_details.email'

        # 2. payment_intent: receipt_email
        receipt_email = data.get('receipt_email')
        logger.info(f'[Email Check 2] receipt_email: {receipt_email}')
        if receipt_email and not email:
            email = receipt_email
            email_source = 'receipt_email'

        # 3. payment_intent: billing_details.email (direct)
        if 'billing_details' in data and data['billing_details']:
            bd_email = data['billing_details'].get('email')
            logger.info(f'[Email Check 3] billing_details.email: {bd_email}')
            if bd_email and not email:
                email = bd_email
                email_source = 'billing_details.email'

        # 4. payment_intent: charges.data[0].billing_details.email
        if 'charges' in data and data['charges'].get('data'):
            charges = data['charges']['data']
            if charges and charges[0].get('billing_details'):
                charge_email = charges[0]['billing_details'].get('email')
                logger.info(f'[Email Check 4] charges[0].billing_details.email: {charge_email}')
                if charge_email and not email:
                    email = charge_email
                    email_source = 'charges[0].billing_details.email'
        else:
            logger.info('[Email Check 4] charges.data: not present')

        # 5. payment_intent: latest_charge.billing_details.email (if expanded)
        if 'latest_charge' in data:
            if isinstance(data['latest_charge'], dict):
                lc = data['latest_charge']
                if lc.get('billing_details'):
                    lc_email = lc['billing_details'].get('email')
                    logger.info(f'[Email Check 5] latest_charge.billing_details.email: {lc_email}')
                    if lc_email and not email:
                        email = lc_email
                        email_source = 'latest_charge.billing_details.email'
            else:
                logger.info(f'[Email Check 5] latest_charge is string ID: {data["latest_charge"]}')
        else:
            logger.info('[Email Check 5] latest_charge: not present')

        # 6. Check for customer object or customer email
        if 'customer_email' in data:
            cust_email = data.get('customer_email')
            logger.info(f'[Email Check 6] customer_email: {cust_email}')
            if cust_email and not email:
                email = cust_email
                email_source = 'customer_email'

        logger.info('=' * 40)
        if contact_id:
            logger.info(f'USING CONTACT ID FROM METADATA: {contact_id}')
        elif email:
            logger.info(f'EMAIL FOUND: {email}')
            logger.info(f'Source: {email_source}')
        else:
            logger.error('NO CONTACT ID OR EMAIL FOUND')
            logger.error('Cannot process payment - need either contactId in metadata or email')
            return
        logger.info('=' * 40)

        # Extract billing details from various sources
        billing_details = {}
        address = {}
        billing_source = 'none'

        # Try billing_details first
        if data.get('billing_details'):
            billing_details = data['billing_details']
            address = billing_details.get('address', {}) or {}
            billing_source = 'billing_details'
            logger.info(f'[Billing] Found in billing_details: {safe_json(billing_details)}')

        # Try charges array for payment_intent
        if not billing_details.get('name') and 'charges' in data and data['charges'].get('data'):
            charges = data['charges']['data']
            if charges and charges[0].get('billing_details'):
                billing_details = charges[0]['billing_details']
                address = billing_details.get('address', {}) or {}
                billing_source = 'charges[0].billing_details'
                logger.info(f'[Billing] Found in charges[0]: {safe_json(billing_details)}')

        # Try customer_details for checkout.session
        if not billing_details.get('name') and 'customer_details' in data:
            customer_details = data.get('customer_details', {}) or {}
            billing_details['name'] = customer_details.get('name')
            if not address:
                address = customer_details.get('address', {}) or {}
            billing_source = 'customer_details'
            logger.info(f'[Billing] Found in customer_details: {safe_json(customer_details)}')

        logger.info(f'[Billing] Final source: {billing_source}')
        logger.info(f'[Billing] Name: {billing_details.get("name", "NOT FOUND")}')
        logger.info(f'[Billing] Address: {safe_json(address)}')

        # Extract amount and convert from cents to dollars
        amount_cents = data.get('amount_total') or data.get('amount') or 0
        amount_dollars = f"{amount_cents / 100:.2f}"
        logger.info(f'[Amount] Cents: {amount_cents} -> Dollars: ${amount_dollars}')

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

        logger.info('-' * 40)
        logger.info('DATA TO SEND TO GHL:')
        logger.info(f'Contact ID: {contact_id}')
        logger.info(f'Email (fallback): {email}')
        logger.info(f'GHL Data: {safe_json(ghl_data)}')
        logger.info('-' * 40)

        # Sync to GHL - prefer contact_id, fallback to email lookup
        sync_to_ghl(ghl_data, contact_id=contact_id, email=email)

    except Exception as e:
        logger.error(f'Error processing payment event: {e}')
        import traceback
        logger.error(f'Traceback:\n{traceback.format_exc()}')


def sync_to_ghl(data, contact_id=None, email=None):
    """Update contact in GHL. Uses contact_id if provided, otherwise looks up by email."""
    logger.info('-' * 40)
    logger.info('SYNCING TO GHL')
    logger.info('-' * 40)

    # Check environment variables
    if not GHL_API_KEY:
        logger.error('GHL_API_KEY is not set!')
        return
    if not GHL_LOCATION_ID:
        logger.error('GHL_LOCATION_ID is not set!')
        return

    logger.info(f'Location ID: {GHL_LOCATION_ID}')
    logger.info(f'API Key: {GHL_API_KEY[:10]}...{GHL_API_KEY[-4:]}' if GHL_API_KEY else 'NOT SET')

    headers = {
        'Authorization': f'Bearer {GHL_API_KEY}',
        'Content-Type': 'application/json',
        'Version': '2021-07-28'
    }

    try:
        # If we don't have a contact_id, look up by email
        if not contact_id:
            if not email:
                logger.error('[GHL] No contact_id or email provided - cannot update')
                return

            logger.info(f'[GHL] No contact_id provided, looking up by email: {email}')
            lookup_url = f'{GHL_BASE_URL}/contacts/?locationId={GHL_LOCATION_ID}&query={email}'
            logger.info(f'[GHL] Looking up contact: {lookup_url}')

            response = requests.get(lookup_url, headers=headers)
            logger.info(f'[GHL] Lookup response status: {response.status_code}')
            logger.info(f'[GHL] Lookup response body: {safe_json(response.json()) if response.status_code == 200 else response.text}')

            if response.status_code != 200:
                logger.error(f'[GHL] Lookup failed: {response.status_code} - {response.text}')
                return

            result = response.json()
            contacts = result.get('contacts', [])

            if not contacts:
                logger.warning(f'[GHL] No contact found for email: {email}')
                logger.info('[GHL] Make sure the contact exists in GHL with this exact email')
                return

            contact = contacts[0]
            contact_id = contact.get('id')
            logger.info(f'[GHL] Found contact via email lookup: {contact_id}')
            logger.info(f'[GHL] Contact name: {contact.get("name", contact.get("firstName", ""))} {contact.get("lastName", "")}')
            logger.info(f'[GHL] Contact email: {contact.get("email")}')
        else:
            logger.info(f'[GHL] Using contact_id from metadata: {contact_id}')

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

        logger.info(f'[GHL] Update payload:\n{safe_json(update_payload)}')

        # Update contact
        update_url = f'{GHL_BASE_URL}/contacts/{contact_id}'
        logger.info(f'[GHL] Updating contact: PUT {update_url}')

        update_response = requests.put(update_url, headers=headers, json=update_payload)
        logger.info(f'[GHL] Update response status: {update_response.status_code}')
        logger.info(f'[GHL] Update response body: {update_response.text[:1000]}')

        if update_response.status_code == 200:
            logger.info('=' * 40)
            logger.info(f'SUCCESS: Updated GHL contact {contact_id}')
            logger.info('=' * 40)
        else:
            logger.error('=' * 40)
            logger.error(f'FAILED: GHL update returned {update_response.status_code}')
            logger.error(f'Response: {update_response.text}')
            logger.error('=' * 40)

    except Exception as e:
        logger.error(f'[GHL] Error syncing to GHL: {e}')
        import traceback
        logger.error(f'Traceback:\n{traceback.format_exc()}')


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    logger.info(f'Starting app on port {port}')
    logger.info(f'GHL Location ID configured: {bool(GHL_LOCATION_ID)}')
    logger.info(f'GHL API Key configured: {bool(GHL_API_KEY)}')
    logger.info(f'Stripe Webhook Secret configured: {bool(STRIPE_WEBHOOK_SECRET)}')
    app.run(host='0.0.0.0', port=port)
