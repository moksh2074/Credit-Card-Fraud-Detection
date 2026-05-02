# IBM Cloud App ID Auth Setup

This app uses IBM Cloud App ID as the identity broker for:

- Cloud Directory email/password login and registration
- Google login through the App ID hosted OAuth flow

The backend exchanges App ID tokens and then issues the existing platform JWT, so the dashboard continues to use the current app auth store.

## IBM Cloud Console

1. Open your IBM Cloud App ID instance.
2. Go to Identity providers.
3. Enable only Cloud Directory and Google.
4. Disable Facebook and any unused providers.
5. In Cloud Directory settings:
   - Choose Email and password.
   - Allow users to sign up.
6. In Google provider settings:
   - Add your Google OAuth client ID.
   - Add your Google OAuth client secret.
7. In Authentication settings, add this web redirect URI:

```text
http://localhost:8000/api/v1/auth/appid/callback
```

For production, add the matching HTTPS backend callback URL.

## Backend Environment

Put these values in `backend/.env`:

```env
IBM_APPID_CLIENT_ID=
IBM_APPID_CLIENT_SECRET=
IBM_APPID_TENANT_ID=
IBM_APPID_OAUTH_SERVER_URL=https://<region>.appid.cloud.ibm.com/oauth/v4/<tenant_id>
IBM_APPID_DISCOVERY_URL=https://<region>.appid.cloud.ibm.com/oauth/v4/<tenant_id>/.well-known/openid-configuration
IBM_APPID_REDIRECT_URI=http://localhost:8000/api/v1/auth/appid/callback
IBM_APPID_IAM_API_KEY=
IBM_APPID_DEFAULT_ROLE=analyst
IBM_APPID_DEFAULT_ORG_ID=org_001
FRONTEND_URL=http://localhost:3000
```

Use `IBM_APPID_IAM_API_KEY` only for Cloud Directory registration from this app. Login and Google OAuth use the App ID client ID and secret.

## Local Verification

1. Start the backend on port `8000`.
2. Start the frontend on port `3000`.
3. Open `/login`.
4. Register with email/password to create a Cloud Directory user.
5. Login with the same email/password.
6. Click Continue with Google and confirm that Google shows the account chooser and continue/cancel screen.
7. After either login path, the app should redirect to `/dashboard`.
