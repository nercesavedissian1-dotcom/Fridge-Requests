# Branch Pantry

Employee stock requests for Bayada, Badaro, Bourj Hammoud and Dekwene. Same Branch Pantry interface, with a Flask backend for Railway and WPS-compatible Excel export.

## Deploy on Railway

1. Upload this folder's contents to a private GitHub repository, keeping `Dockerfile` at the repository root.
2. Create a separate Railway project and deploy the repository's `main` branch.
3. Attach a persistent volume at `/data`. Requests are stored in `/data/requests.db`; keep this volume attached across redeployments.
4. Set `OWNER_PASSWORD` to your owner password and `SESSION_SECRET` to a long random secret. Set `DATA_DIR=/data`. Railway provides `PORT` automatically. Never commit secret values.
5. Generate a Railway domain. Employees use the main request page. Owner signs in under Request history to review requests and download the workbook.

The workbook has four sheets, automatic Beirut dates, employee name, category, item, quantity, notes and request ID. Download it from Request history → Download for WPS and open the `.xlsx` in WPS Spreadsheets. Saving requests is automatic; updating a file already open on your computer is not automatic.

## Development

Python 3.12 and Node 22 are used by the Dockerfile. Install `requirements.txt`, then run `npm ci && npm run build` inside `frontend`. Copy `frontend/dist` to `static` before starting Flask locally. Configure `OWNER_PASSWORD` and `SESSION_SECRET`; `DATA_DIR` defaults to a local `data` directory. Run `gunicorn --bind 127.0.0.1:8080 app:app`.

No live request records or credentials are included in this package.
