#!/usr/bin/env node

const { PublicClientApplication } = require('@azure/msal-node');
require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });

const tenantId = process.env.SMTP_TENANT_ID || process.env.AZURE_TENANT_ID;
const clientId = process.env.SMTP_CLIENT_ID || process.env.AZURE_CLIENT_ID;

if (!tenantId || !clientId) {
  console.error('Missing Azure app registration values.');
  console.error('Add to .env:');
  console.error('SMTP_TENANT_ID=<tenant-id>');
  console.error('SMTP_CLIENT_ID=<app-registration-client-id>');
  console.error('');
  console.error('Then run:');
  console.error('npm run get-smtp-token');
  process.exit(1);
}

async function main() {
  const pca = new PublicClientApplication({
    auth: {
      clientId,
      authority: `https://login.microsoftonline.com/${tenantId}`
    }
  });

  const result = await pca.acquireTokenByDeviceCode({
    deviceCodeCallback: (response) => {
      console.log('');
      console.log('Open this URL in your browser:');
      console.log(response.verificationUri);
      console.log('Enter the code below:');
      console.log(response.userCode);
      console.log('');
      console.log('After signing in, the script will print the SMTP token details.');
    },
    scopes: [
      'https://outlook.office.com/SMTP.Send',
      'offline_access',
      'openid',
      'profile'
    ]
  });

  const expiresAt = result.expiresOn ? result.expiresOn.getTime() : null;

  console.log('');
  console.log('SUCCESS');
  console.log('Access token acquired for Microsoft 365 / Outlook SMTP.');
  console.log('');
  console.log('Add these values to your .env file:');
  console.log(`SMTP_AUTH_TYPE=oauth2`);
  console.log(`SMTP_CLIENT_ID=${clientId}`);
  console.log(`SMTP_TENANT_ID=${tenantId}`);
  console.log(`SMTP_ACCESS_TOKEN=${result.accessToken}`);
  console.log(`SMTP_ACCESS_TOKEN_EXPIRES_AT=${expiresAt}`);
  console.log(`SMTP_REFRESH_TOKEN=${result.refreshToken || ''}`);
  console.log('');
  console.log('Keep the refresh token in a secure secret store and do not commit it to source control.');
}

main().catch((error) => {
  console.error('Unable to get token.');
  console.error(error.message || error);
  process.exit(1);
});
