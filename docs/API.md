# EarthScope API

The API is a read-only interface for the existing processed EarthScope outputs. It does not replace the Streamlit dashboard or change the scientific analysis pipeline.

## Run locally

Install the repository dependencies, then start the service from the repository root:

```bash
python -m pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Interactive API documentation is available at `/docs`.

## Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Service and processed-data availability |
| GET | `/api/v1/locations` | Configured study locations and coordinates |
| GET | `/api/v1/variables` | Supported NASA POWER variables and units |
| GET | `/api/v1/metadata` | Processed dataset provenance and coverage metadata |
| GET | `/api/v1/trends` | Existing trend results, with optional filters |

Trend filters:

- `location`: one configured location, such as `Accra`
- `variable`: one supported variable code, such as `T2M`
- `significant_only`: `true` to return only FDR-significant results

Example:

```text
/api/v1/trends?location=Accra&variable=T2M
```

## CORS

The default allowed origins are the LumosX production site and local Vite development origins. Override them with a comma-separated `LUMOSX_ALLOWED_ORIGINS` environment variable when deploying.

## Scientific interpretation

The historical climate products served here are monthly NASA POWER gridded estimates, not direct weather-station observations. Trend results retain the source fields, units, coverage, statistical method, p-values, FDR-adjusted p-values and evidence classification from the existing analysis.

The API currently exposes existing processed trend outputs. It does not fetch new NASA POWER data, run new analyses, or claim continuous gridded spatial trend coverage.

## Render deployment

The Render web service is configured to deploy from the `feature/lumosx-api-foundation` branch using `requirements-api.txt` and `uvicorn api.main:app --host 0.0.0.0 --port $PORT`. Automatic deployment is enabled for commits pushed to that branch.

After deployment, verify `/api/v1/health`, `/api/v1/locations`, `/api/v1/variables`, `/api/v1/metadata`, and a filtered `/api/v1/trends` request before configuring the LumosX frontend.
