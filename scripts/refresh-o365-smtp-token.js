#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { PublicClientApplication, ConfidentialClientApplication } = require('@azure/msal-node');
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });

const envPath = path.join(__dirname, '..', '.env');
const tenantId = process.env.SMTP_TENANT_ID || process.env.AZURE_TENANT_ID;
const clientId = process.env.SMTP_CLIENT_ID || process.env.AZURE_CLIENT_ID;
const clientSecret = process.env.SMTP_CLIENT_SECRET;
const refreshToken = process.env.SMTP_REFRESH_TOKEN;

function writeEnvValue(key, value) {
  const content = fs.readFileSync(envPath, 'utf8');
  const reg = new RegExp(`^${key}=.*$`, 'm');
  if (reg.test(content)) {
    fs.writeFileSync(envPath, content.replace(reg, `${key}=${value}`));
    return;
  }

  fs.writeFileSync(envPath, `${content.trim()}\n${key}=${value}\n`);
}

async function main() {
  if (!tenantId || !clientId) {
    console.error('Missing SMTP_TENANT_ID or SMTP_CLIENT_ID in .env');
    process.exit(1);
  }

  if (!refreshToken) {
    console.error('Missing SMTP_REFRESH_TOKEN in .env. Run npm run get-smtp-token first to generate one.');
    process.exit(1);
  }

  const msalConfig = {
    auth: {
      clientId,
      authority: `https://login.microsoftonline.com/${tenantId}`
    }
  };

  if (clientSecret) {
    msalConfig.auth.clientSecret = clientSecret;
  }

  const app = clientSecret
    ? new ConfidentialClientApplication(msalConfig)
    : new PublicClientApplication(msalConfig);

  const result = await app.acquireTokenByRefreshToken({
    refreshToken,
    scopes: ['https://outlook.office.com/SMTP.Send', 'offline_access', 'openid', 'profile']
  });

  if (!result || !result.accessToken) {
    throw new Error('No access token returned from Microsoft 365 refresh flow.');
  }

  const expiresAt = result.expiresOn ? result.expiresOn.getTime() : Date.now() + 3600000;
  writeEnvValue('SMTP_ACCESS_TOKEN', result.accessToken);
  writeEnvValue('SMTP_ACCESS_TOKEN_EXPIRES_AT', String(expiresAt));

  console.log('SUCCESS');
  console.log('New SMTP access token stored in .env');
  console.log(`SMTP_ACCESS_TOKEN_EXPIRES_AT=${expiresAt}`);
}

main().catch((error) => {
  console.error('Unable to refresh token.');
  console.error(error.message || error);
  process.exit(1);
});
