# Stripe to GoHighLevel Sync

A Python Flask webhook server for Railway that syncs Stripe payment data to GoHighLevel (GHL) contacts.

## Overview

This service listens for Stripe webhook events and automatically updates GoHighLevel contact custom fields with payment and billing information.

### Supported Events
- `checkout.session.completed`
- - `payment_intent.succeeded`
 
  - ### Data Synced to GHL
  - - Card holder name
    - - Billing address (line 1, line 2, city, state, country)
      - - Total payment amount
       
        - ## Quick Start
       
        - 1. Clone this repository
          2. 2. Copy `.env.example` to `.env` and fill in your credentials
             3. 3. Deploy to Railway (see SETUP_GUIDE.md for detailed instructions)
               
                4. ## Environment Variables
               
                5. | Variable | Description |
                6. |----------|-------------|
                7. | `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret (starts with `whsec_`) |
                8. | `GHL_API_KEY` | GoHighLevel API key |
               
                9. ## Project Structure
               
                10. ```
                    stripe-ghl-sync/
                    ├── app.py              # Main Flask application
                    ├── requirements.txt    # Python dependencies
                    ├── Procfile           # Process configuration for Railway
                    ├── railway.toml       # Railway deployment configuration
                    ├── .env.example       # Environment variables template
                    ├── README.md          # This file
                    └── SETUP_GUIDE.md     # Detailed setup instructions
                    ```

                    ## Endpoints

                    | Endpoint | Method | Description |
                    |----------|--------|-------------|
                    | `/webhook` | POST | Receives Stripe webhook events |
                    | `/health` | GET | Health check endpoint (returns 200) |

                    ## Troubleshooting

                    ### Webhook returns 400
                    - Verify your `STRIPE_WEBHOOK_SECRET` is correct
                    - - Ensure the webhook is configured in Stripe dashboard
                     
                      - ### Contact not updating in GHL
                      - - Check if the contact exists in GHL with the same email
                        - - Verify your `GHL_API_KEY` has correct permissions
                          - - Check Railway logs for error messages
                           
                            - ### Custom fields not appearing
                            - - Ensure custom fields exist in GHL with exact names
                              - - Field keys in GHL may differ from display names
                               
                                - ## License
                               
                                - MIT
