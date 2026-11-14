# EarthScope Web

The Vercel-hosted public web experience for EarthScope.

## Architecture

- This directory is the Vercel project root.
- The current Streamlit application remains available at https://earthscope.streamlit.app/.
- The web experience provides a responsive public entry point and links visitors to the existing analysis dashboard.
- The Python analysis engine and original Streamlit dashboard remain in the repository root and are not modified by this frontend.

## Local development

```bash
npm install
npm run dev
```

## Deployment

Vercel should use this directory as its Root Directory, with the Next.js framework preset.
