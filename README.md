# Bulk Certificate Generator

I built this for one real situation. After a workshop or a course, someone has a list of people and wants a certificate for each of them. They should not have to call the API once per person. They send the list once. I generate the PDFs, keep a status for every person, and let them download the files when they are ready.

One bad row does not cancel the rest of the list. If Priya's email is wrong, Rahul still gets his certificate.

Open the app and the certificate is on the screen. Generate the batch and click a name to see that person's copy.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

The form is already filled with a sample batch. Click **Generate certificates**. The preview on top changes to the real PDF for that person. **PDF** downloads the file. **Verify** opens the public check page. **Download zip** is every successful certificate. **Download CSV** is the full result, including the rows that failed.

API reference: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

Python 3.11 or newer. No database server. SQLite is created at `data/certificates.db`. PDFs go to `storage/certificates/`.

```bash
pytest
```

Optional:

```bash
cp .env.example .env          # only if you want to change settings
python -m app.preview         # rewrites examples/sample-certificate.pdf
./scripts/demo.sh             # posts the sample and saves a zip and a csv
```

Docker, if you want it:

```bash
docker build -t certificate-generator .
docker run --rm -p 8000:8000 certificate-generator
```

## What the certificate contains

There is one template. I did not build a template editor, and I did not add a second design. `app/services/pdf.py` draws it.

Every certificate has:

- the organisation name
- "Certificate of Completion"
- the person's name
- a short line such as "has successfully completed"
- the event or course title
- an optional detail line, like a grade or a track
- the signatory
- the date
- a certificate number, for example `CERT-2026-92A72A064E42`
- a QR code that opens the public verify page

The email and the caller's own id are stored for the organiser. They are not printed. The public verify page also does not return them. If someone scans the QR code, they can check that the certificate is real. They should not see the person's email.

The font is DejaVu. It covers Latin, Greek, and Cyrillic. If a name has a character the font cannot draw, that one person fails and the others still go through. The license is in `app/fonts/LICENSE`.

## How you call it

`POST /api/v1/jobs` takes the whole list. The response is `202` and a job id. The PDFs are made after that response is sent.

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: workshop-2026-10-08" \
  --data-binary @examples/request.json
```

The body has two parts.

The event is shared by everyone:

| Field | Required | What I do with it |
| --- | --- | --- |
| `title` | yes | Printed as the course or event name |
| `issuer` | yes | The organisation on the certificate |
| `issue_date` | yes | The date on the certificate |
| `description` | no | The line under the name. If you leave it out I use "has successfully completed" |
| `signatory_name` | no | If empty, I print the issuer name |
| `signatory_title` | no | If empty, I print "Authorized signatory" |

Each person:

| Field | Required | What I do with it |
| --- | --- | --- |
| `name` | yes | Printed in large type |
| `email` | no | Saved for the CSV. Not printed. Not on the public verify page |
| `external_id` | no | Your own reference. Unique inside this request. Not printed |
| `detail` | no | One extra line on that person's certificate only |

Then:

```bash
curl -sS http://127.0.0.1:8000/api/v1/jobs/JOB_ID
curl -sS "http://127.0.0.1:8000/api/v1/jobs/JOB_ID/certificates?status=failed"
curl -sS -o ada.pdf http://127.0.0.1:8000/api/v1/certificates/CERTIFICATE_ID/download
curl -sS -o certificates.zip http://127.0.0.1:8000/api/v1/jobs/JOB_ID/archive
curl -sS -o report.csv http://127.0.0.1:8000/api/v1/jobs/JOB_ID/report
curl -sS http://127.0.0.1:8000/api/v1/verify/CERT-2026-92A72A064E42
```

`?inline=true` on the download URL shows the PDF in the browser. The page uses `/preview.png` so you can see the certificate without a PDF plugin.

If you send the same `Idempotency-Key` with the same body, I return the original job with `200`. I do not generate a second batch. If the body is different, I return `409`.

`callback_url` is optional. I POST the job summary there when the job finishes. If that call fails, the job still stays completed. The files are already saved.

## High level design

The browser page is only a client. The assignment is the API. The page posts to the same endpoints a script would use.

```mermaid
flowchart LR
    client[Browser or curl]
    api[FastAPI]
    db[(SQLite or Postgres)]
    worker[Worker thread]
    disk[PDF folder]

    client -->|POST /jobs| api
    api -->|save job and people| db
    api -->|202 job id| client
    worker -->|claim oldest queued job| db
    worker -->|write one PDF| disk
    worker -->|commit that person's result| db
    client -->|GET /jobs/id| api
    api -->|progress| client
    client -->|download PDF, zip, or CSV| api
    api -->|read file| disk
```

Why it is split like this:

The HTTP request should return quickly. Drawing a few hundred PDFs can take a while, and the caller also needs a way to ask "how far along is it?". So I save the job first and return `202`. A worker in the same process picks the job up and does the drawing.

I did not add Redis or Celery. A reviewer should be able to run this with Python only. The function that actually does the work is `process_job` in `app/services/jobs.py`. The thread only calls that function. The tests call the same function. If this later moves to a real queue, that function does not have to change.

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant DB
    participant Worker
    Client->>API: POST /api/v1/jobs
    API->>DB: insert job and one row per person
    API-->>Client: 202 and job id
    Worker->>DB: claim the job if it is still queued
    loop each pending person
        Worker->>Worker: draw the PDF
        Worker->>DB: commit success or failure
    end
    Client->>API: GET /api/v1/jobs/{id}
    API-->>Client: counts and status
    Client->>API: GET certificate download
    API-->>Client: the PDF
```

## Low level design

Two tables.

`generation_jobs` is the thing the client polls.

| Column | Why it is there |
| --- | --- |
| `id` | UUID. This is the job id in the URL |
| `status` | queued, processing, completed, completed_with_errors, or failed |
| event fields | title, issuer, date, description, signatory |
| `total_count`, `pending_count`, `success_count`, `failure_count` | The progress numbers. I update them as I go |
| `idempotency_key`, `payload_hash` | So a retry does not create a second job |
| `callback_url` | Where to POST when the job is done |
| `started_at`, `completed_at` | So you can see it actually ran |

`certificates` is one row per person.

| Column | Why it is there |
| --- | --- |
| `position` | The order they were sent in |
| `recipient_name`, `email`, `external_id`, `detail` | What the client sent |
| `status` | pending, succeeded, or failed |
| `failure_stage` | `validation` or `generation`, so you know which step broke |
| `error_message` | What to show the client |
| `certificate_number` | The public number, only after success |
| `file_path` | Where the PDF is. I never return this path in the API |

The file name on disk is the certificate id, not the person's name. Names have spaces and characters that do not belong in a path.

### What happens on POST /jobs

1. If there is an idempotency key, I look it up first. Same body means return the old job. Different body means `409`.
2. I reject the whole request when the list is empty, the event is invalid, the date is nonsense, or the list is over the limit. Default limit is 500. Nothing is saved.
3. I check each person on their own. Name has to be a real name. Email has to look like an email if they sent one. `external_id` cannot repeat inside this request.
4. If nobody is valid, I return `422` and I do not create a job. There is nothing to track.
5. If some people are invalid, I still create the job. Those rows are already `failed` with `failure_stage = validation`. The valid rows are `pending`.
6. I commit, then return `202`.

I split it this way on purpose. A missing event title is a mistake in the call itself, so the client should fix the call. A bad email on person 40 of 200 should not force them to resend the other 199.

### What the worker does

1. On startup, any job left in `processing` goes back to `queued`. That is a crash from last time. Finished PDFs stay finished.
2. It picks the oldest queued job.
3. It updates that row to `processing` only if the status is still `queued`. If two processes read the same id, only one update matches. The other one leaves it alone.
4. For each pending person it draws the PDF, then commits that row before starting the next person. A poll in the middle of a big batch shows real numbers, not a guess.
5. At the end:
   - everyone succeeded: `completed`
   - some succeeded and some failed: `completed_with_errors`
   - nobody succeeded: `failed`
6. If a callback URL was sent, I POST the summary. A network error there does not change the job.

If drawing one PDF throws, I mark that person failed and I continue. A known problem, like a character the font cannot draw, is saved as the message. An unexpected error is logged on the server, and the client sees a fixed sentence. I do not send them a stack trace.

### The code, file by file

| File | What I would open it for |
| --- | --- |
| `app/main.py` | App startup, the home page, error shape |
| `app/api/routes/jobs.py` | Create a job, poll it, zip, CSV |
| `app/api/routes/certificates.py` | One certificate, the PDF, the preview image |
| `app/api/routes/verify.py` | Public check. JSON for scripts, HTML for a browser |
| `app/schemas.py` | The request and response shapes |
| `app/models.py` | The two tables |
| `app/services/validation.py` | The per-person rules |
| `app/services/jobs.py` | Create, claim, and generate. This is the core |
| `app/services/pdf.py` | The certificate drawing |
| `app/services/worker.py` | The thread. It only claims and calls `process_job` |
| `app/services/exports.py` | Zip and CSV |
| `app/static/index.html` | The page. It calls the API. It does not generate PDFs |
| `tests/` | The behaviour I care about |

If you ask me to change the look of the certificate, I change `pdf.py` and run `python -m app.preview`.

If you ask me to add a field, I add it in `schemas.py`, store it in `models.py`, pass it into `render_certificate`, and add it to the response in `serializers.py`.

If you ask me to reject a new kind of bad input, I add a `FieldIssue` in `validation.py`. I do not raise and abort the batch.

## Settings

Copy `.env.example` to `.env` only when a default is wrong.

| Variable | Default | What it does |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/certificates.db` | Swap this for Postgres. The code stays the same |
| `STORAGE_DIR` | `./storage/certificates` | Where the PDFs go |
| `PUBLIC_BASE_URL` | `http://127.0.0.1:8000` | Used in links and in the QR code |
| `MAX_RECIPIENTS_PER_JOB` | `500` | Hard cap on one request |
| `WORKER_ENABLED` | `true` | `false` saves jobs and does not generate them |
| `WORKER_POLL_INTERVAL_SECONDS` | `0.5` | How often an idle worker looks for work |
| `API_KEY` | empty | When set, job and certificate routes need header `X-API-Key` |
| `CORS_ORIGINS` | `*` | Browser origins, comma separated |

Health and verify stay open even when the API key is set. A printed QR code cannot send a secret.

Postgres:

```bash
pip install "psycopg[binary]"
```

```text
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/certificates
```

Tables are created on startup. I used `create_all` because this schema is small and the reviewer should not have to run a migration tool. If this database lived for a long time and the tables had to change, I would add Alembic before the first real change.

On Postgres the claim query also uses `FOR UPDATE SKIP LOCKED`, so more than one worker can run without taking the same job.

## Tests

```bash
pytest
```

The tests use a temporary database and a temporary folder. They do not start the background thread. They call the worker function, so the tests do not depend on a sleep.

| What the assignment asked for | Test file |
| --- | --- |
| Create a job | `tests/test_create_job.py` |
| Validation | `tests/test_validation.py` |
| Generate the certificate | `tests/test_generation.py` |
| Status and progress | `tests/test_status.py` |
| One failure does not stop the others | `tests/test_failure.py` |
| Download the files | `tests/test_retrieval.py` |

I also test the public verify page, idempotency, the callback, the API key, restart recovery, and two claims on the same job.

## A few things I would say if asked

**Why not generate inside the request?**
Because the caller needs progress, and a long list should not hold the connection open. The job row is the progress.

**Why does one bad email not return 422 for the whole list?**
Because the useful part of a bulk API is that person 40 being wrong does not make me throw away the other 199. I still tell the client exactly which row failed, in `validation_issues` and on that certificate row. If every row is bad, then I do return 422 and I do not create a job.

**What if the process dies halfway?**
Each person is committed before the next one starts. On the next startup I put `processing` jobs back to `queued` and I only draw the people who are still pending.

**Why is the verify page public?**
The QR code is printed on the certificate. The person holding the paper does not have the API key. The number itself is random, 12 hex characters plus the year, so it is not something you can guess by walking the ids.

**What I left out on purpose**
Callback hosts are not on an allowlist. HTTP and HTTPS are allowed, and I do not follow redirects. That is fine for a demo. Before this took jobs from strangers, I would only call hosts the organiser configured. Files are on local disk. `app/services/paths.py` is where I would switch that to object storage. The download path is checked so it cannot escape `STORAGE_DIR`. CSV cells that start with `=`, `+`, `-`, or `@` get a quote in front, so a name cannot become a spreadsheet formula.
