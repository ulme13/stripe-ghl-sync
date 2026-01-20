# Setup Guide

Complete step-by-step instructions for setting up the Stripe to GoHighLevel sync.

## 1. GHL Custom Fields Setup

Before deploying, you need to create custom fields in GoHighLevel to store Stripe data.

### Create Custom Fields

1. Log into GoHighLevel
2. 2. Navigate to **Settings** > **Custom Fields** > **Contact**
   3. 3. Click **Add Field** and create each of the following:
     
      4. | Display Name | Field Type | Notes |
      5. |--------------|------------|-------|
      6. | Stripe Card Name | Text | Stores billing name |
      7. | Stripe Card Address Line 1 | Text | Street address |
      8. | Stripe Card Address Line 2 | Text | Apt/Suite number |
      9. | Stripe Card City | Text | City |
      10. | Stripe Card State | Text | State/Province |
      11. | Stripe Card Country | Text | Country code |
      12. | Stripe Total Spend | Text | Total amount paid |
     
      13. ### Finding Field Keys
     
      14. After creating custom fields, you need the **field keys** (not display names):
     
      15. 1. Go to **Settings** > **Custom Fields** > **Contact**
          2. 2. Click on a field to edit it
             3. 3. Look for the **Field Key** - this is what the API uses
                4. 4. Common format: `stripe_card_name`, `stripe_card_address_line_1`, etc.
                  
                   5. **Important:** If your field keys differ from the defaults in `app.py`, update the `customField` mapping in the `sync_to_ghl` function.
                  
                   6. ## 2. GHL API Key
                  
                   7. ### For Sub-Account (Location)
                  
                   8. 1. Log into your GHL sub-account
                      2. 2. Go to **Settings** > **Business Profile**
                         3. 3. Scroll to **API Keys** section
                            4. 4. Click **Generate New Key**
                               5. 5. Copy the API key
                                 
                                  6. ### For Agency Account
                                 
                                  7. If using an Agency account, you may need to use OAuth:
                                 
                                  8. 1. Go to **Agency Settings** > **Developer**
                                     2. 2. Create an OAuth app
                                        3. 3. Follow the OAuth flow to get an access token
                                          
                                           4. ## 3. Railway Deployment
                                          
                                           5. ### Connect GitHub Repository
                                          
                                           6. 1. Log into [Railway](https://railway.com)
                                              2. 2. Click **New Project**
                                                 3. 3. Select **Deploy from GitHub repo**
                                                    4. 4. Authorize Railway to access your GitHub
                                                       5. 5. Select the `stripe-ghl-sync` repository
                                                          6. 6. Railway will automatically detect it as a Python project
                                                            
                                                             7. ### Add Environment Variables
                                                            
                                                             8. 1. In your Railway project, click on the service
                                                                2. 2. Go to the **Variables** tab
                                                                   3. 3. Add the following variables:
                                                                     
                                                                      4. ```
                                                                         STRIPE_WEBHOOK_SECRET=whsec_your_secret_here
                                                                         GHL_API_KEY=your_ghl_api_key_here
                                                                         ```

                                                                         ### Deploy

                                                                         1. Railway will automatically deploy when you add variables
                                                                         2. 2. Wait for the build to complete
                                                                            3. 3. Click **Settings** > **Networking**
                                                                               4. 4. Copy your Railway public URL (e.g., `https://your-app.railway.app`)
                                                                                 
                                                                                  5. ## 4. Stripe Webhook Setup
                                                                                 
                                                                                  6. 1. Log into [Stripe Dashboard](https://dashboard.stripe.com)
                                                                                     2. 2. Go to **Developers** > **Webhooks**
                                                                                        3. 3. Click **Add endpoint**
                                                                                           4. 4. Enter your endpoint URL: `https://your-railway-url.railway.app/webhook`
                                                                                              5. 5. Select events to listen to:
                                                                                                 6.    - `checkout.session.completed`
                                                                                                       -    - `payment_intent.succeeded`
                                                                                                            - 6. Click **Add endpoint**
                                                                                                              7. 7. Copy the **Signing secret** (starts with `whsec_`)
                                                                                                                 8. 8. Add this secret to Railway as `STRIPE_WEBHOOK_SECRET`
                                                                                                                   
                                                                                                                    9. ## 5. Testing
                                                                                                                   
                                                                                                                    10. ### Local Testing with Stripe CLI
                                                                                                                   
                                                                                                                    11. 1. Install Stripe CLI: https://stripe.com/docs/stripe-cli
                                                                                                                        2. 2. Login: `stripe login`
                                                                                                                           3. 3. Forward webhooks to local:
                                                                                                                              4.    ```bash
                                                                                                                                       stripe listen --forward-to localhost:5000/webhook
                                                                                                                                       ```
                                                                                                                                    4. Copy the webhook signing secret shown
                                                                                                                                    5. 5. Run your Flask app locally:
                                                                                                                                       6.    ```bash
                                                                                                                                                python app.py
                                                                                                                                                ```
                                                                                                                                             6. Trigger a test event:
                                                                                                                                             7.    ```bash
                                                                                                                                                      stripe trigger payment_intent.succeeded
                                                                                                                                                      ```
                                                                                                                                                   
                                                                                                                                                   ### Verify in GHL
                                                                                                                                               
                                                                                                                                               1. Create a test contact in GHL with the email used in Stripe
                                                                                                                                               2. 2. Make a test payment in Stripe
                                                                                                                                                  3. 3. Check the contact's custom fields in GHL
                                                                                                                                                     4. 4. Verify the billing data was synced
                                                                                                                                                       
                                                                                                                                                        5. ### Check Railway Logs
                                                                                                                                                       
                                                                                                                                                        6. 1. In Railway, click on your service
                                                                                                                                                           2. 2. Go to **Deployments** > select latest deployment
                                                                                                                                                              3. 3. Click **View Logs**
                                                                                                                                                                 4. 4. Look for log messages indicating successful syncs or errors
                                                                                                                                                                   
                                                                                                                                                                    5. ## Common Issues
                                                                                                                                                                   
                                                                                                                                                                    6. ### "Invalid signature" error
                                                                                                                                                                    7. - Make sure `STRIPE_WEBHOOK_SECRET` matches the signing secret from Stripe
                                                                                                                                                                       - - Ensure you're using the correct webhook endpoint signing secret (not the API key)
                                                                                                                                                                        
                                                                                                                                                                         - ### "Contact not found" in logs
                                                                                                                                                                         - - The email from Stripe must exactly match a contact email in GHL
                                                                                                                                                                           - - Create the contact in GHL first, then make the Stripe payment
                                                                                                                                                                            
                                                                                                                                                                             - ### Custom fields not updating
                                                                                                                                                                             - - Verify the field keys in `app.py` match your GHL custom field keys
                                                                                                                                                                               - - Check that your GHL API key has write permissions
                                                                                                                                                                                
                                                                                                                                                                                 - ### Health check failing
                                                                                                                                                                                 - - Verify the `/health` endpoint returns 200
                                                                                                                                                                                   - - Check Railway deployment logs for errors
