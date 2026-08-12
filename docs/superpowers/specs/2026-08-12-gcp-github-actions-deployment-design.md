# GCP GitHub Actions Deployment Design

## Goal

Deploy the A-Math Telegram bot as a cost-conscious pilot on Google Cloud and automatically
release every successful push to the GitHub `deploy` branch. Keep application secrets out of
GitHub and avoid long-lived Google Cloud credentials.

## Current constraints

- The bot is one continuously running Python 3.12 process using Telegram long polling.
- The process also owns the minute-based assignment scheduler and three-second marking worker.
- Exactly one bot replica may run during the pilot.
- PostgreSQL 16 is the production database.
- The checked-in Docker image contains the question and solution assets and runs as an
  unprivileged user.
- The deployment region is `asia-southeast1`, with a Compute Engine zone in Singapore.
- The Google Cloud project ID and display name are `chloe-tutoring-bot`.
- The deployment must prioritize low pilot cost over high availability.

## Architecture

Use one small Compute Engine VM for the bot and one zonal Cloud SQL for PostgreSQL instance.
Artifact Registry stores immutable container images. Secret Manager stores all application and
database credentials. A dedicated VM service account reads only the required secrets and images.

GitHub Actions is the release controller. Every push to `deploy` runs the complete quality suite.
Only a successful suite may authenticate to Google Cloud, build an image, and deploy it. GitHub
uses Workload Identity Federation and short-lived credentials; no service-account key is created
or stored in GitHub.

The VM accepts no public application traffic. It initiates outbound connections to Telegram,
OpenRouter, Google APIs, and Cloud SQL. Administrative deployments use Identity-Aware Proxy and
OS Login instead of exposing SSH to the internet.

## Google Cloud resources

Provision these resources explicitly rather than on every release:

- Project `chloe-tutoring-bot`, linked to the available billing account.
- Required Compute Engine, Cloud SQL, Artifact Registry, Secret Manager, IAM Credentials,
  Security Token Service, IAP, OS Login, and Cloud Build APIs.
- Artifact Registry Docker repository in `asia-southeast1`.
- One zonal Cloud SQL PostgreSQL 16 Enterprise instance with the smallest suitable pilot shape,
  automatic storage growth, automated backups, point-in-time recovery where the selected shape
  supports it, and deletion protection.
- One small Compute Engine VM in Singapore with automatic restart and no public application
  ports. Begin with an economical machine type and resize if PDF/marking workloads exhaust memory.
- A private database connection when it can be provisioned without disproportionate pilot
  complexity or fixed networking cost. Otherwise, use the Cloud SQL Auth Proxy on the VM so the
  database is never opened to arbitrary source addresses.
- Separate least-privilege service accounts for the VM and GitHub deployment workflow.
- A Workload Identity Pool and GitHub OIDC provider restricted to
  `stellarsable7/tutoring-bot`, with deployment impersonation restricted to the `deploy` branch.

Application secrets in Secret Manager:

- Telegram bot token.
- Numeric tutor Telegram ID.
- Review callback secret of at least 32 characters.
- OpenRouter API key.
- Database username/password or complete async SQLAlchemy database URL, depending on the final
  Cloud SQL connection mechanism.

GitHub repository variables hold non-secret identifiers such as project ID, region, zone,
repository name, VM name, and deployment service-account name. Application secrets do not enter
GitHub Actions logs or GitHub Secrets.

## Repository changes

Add narrowly scoped deployment artifacts:

- A production Docker entrypoint or command that starts only the bot.
- A deployment script installed on or invoked against the VM. It accepts an exact image digest
  or commit-SHA tag, retrieves secrets without printing them, runs migrations, replaces the
  singleton container, verifies startup, and restores the prior application image on failure.
- A one-time infrastructure bootstrap script or declarative configuration for reproducible GCP
  provisioning.
- A GitHub Actions validation workflow for pull requests and non-deployment pushes.
- A deployment workflow triggered by pushes to `deploy`.
- Deployment and rollback instructions in the operations documentation.
- The reviewed catalogue data must be copied into the image so catalogue import can be run in the
  deployed environment.

The current untracked `diegos_prompts/` directory and `docs/ARCHITECTURE.md` file are outside this
work and must remain untouched.

## Continuous deployment flow

For each push to `deploy`:

1. Check out the exact commit.
2. Install locked Python dependencies.
3. Run `pytest -q`, Ruff over `src` and `tests`, and strict mypy over `src`.
4. Authenticate to Google Cloud through GitHub OIDC and Workload Identity Federation.
5. Build the Docker image from the exact commit and push it to Artifact Registry with the full
   Git commit SHA. Record and deploy the resulting immutable image digest.
6. Connect to the VM through IAP with OS Login and invoke the deployment script with that digest.
7. Pull the new image before interrupting the running bot.
8. Validate required configuration without revealing values.
9. Run `alembic upgrade head` as a one-off container against Cloud SQL.
10. Stop the old bot and start exactly one container from the new digest.
11. Confirm that the container remains running and logs `starting Telegram polling` within a
    bounded timeout.
12. Report the deployed commit and image digest in the GitHub Actions job summary.

The workflow uses GitHub Actions concurrency with cancellation disabled. This serializes releases
so two rapid pushes cannot operate on the singleton simultaneously. A later commit waits for the
active deployment instead of cancelling it midway.

## Migration and rollback policy

Database migrations are separated from normal bot startup. The deployment script executes
`alembic upgrade head` before replacing the running application. A migration failure leaves the
old bot running and fails the workflow.

After a successful migration, the new bot replaces the old one. If the new container does not
become healthy, the script restarts the previously deployed image and exits non-zero. Schema
migrations must therefore be backward-compatible with the immediately previous application
release. Automated deployment does not run Alembic downgrades.

The VM records the last successfully deployed image digest in a root-owned state file. Operators
can invoke the same deployment script with a known digest for a deliberate rollback.

The bot uses long polling, so replacement creates a brief interruption. The database-backed
assignment uniqueness constraints and persisted marking retry deadlines make process restart
safe. The script must never allow the old and new polling containers to overlap.

## Security and privacy

- Workload Identity Federation replaces downloadable Google service-account keys.
- The GitHub identity condition binds deployment access to the expected repository and `deploy`
  branch.
- IAM roles are granted at the narrowest practical resource scope.
- Secrets are fetched directly on the VM into a root-readable temporary environment file or
  equivalent runtime mechanism and are removed after container creation when safe.
- Commands must not interpolate secret values into GitHub Actions output, VM metadata, process
  arguments, or shell history.
- Cloud SQL has no unrestricted public ingress.
- The VM exposes no bot HTTP endpoint and needs no inbound application firewall rule.
- Student names, Telegram IDs, submissions, OCR text, and tokens must not appear in deployment
  logs or metric labels.
- Cloud SQL backups follow the same retention and privacy rules as primary student records.

## Cost controls

- Use one zonal VM and one zonal database; do not provision an HA database standby or multi-zone
  application group for the pilot.
- Start with the smallest VM that can reliably build no artifacts locally and run the bot's PDF,
  symbolic, and network workload. Artifact builds occur in Cloud Build, not on the VM.
- Configure budget alerts in the billing account for early warning. Budget alerts do not enforce
  a hard spending cap.
- Configure Artifact Registry cleanup for old untagged images while retaining deployed and recent
  rollback digests.
- Prefer resource resizing based on measured memory, CPU, database, and storage use.

## Verification and acceptance

Before the first live deployment:

- The local and GitHub quality suites pass.
- A dry-run container validates required settings without contacting Telegram.
- Alembic reaches `head` on Cloud SQL.
- The reviewed catalogue passes dry-run import and is imported once.
- The running container uses the intended immutable digest and logs polling startup.
- The VM restart policy brings back exactly one bot container after a reboot.
- A failed test prevents image deployment.
- A deliberately invalid application image exercises rollback without changing database schema.
- A second queued deployment cannot overlap the first.
- The tutor verifies `/help`, `/students`, `/invite`, and one end-to-end pilot interaction.
- Cloud SQL backup settings, deletion protection, Secret Manager access, IAM bindings, and the
  absence of public application ingress are inspected after provisioning.

## Operations

Every successful push to `deploy` is a production release. Changes should reach `deploy` through
reviewed commits, and branch protection should require the validation checks where the GitHub
plan permits it.

Infrastructure changes remain explicit and are not automatically applied by application pushes.
Secret rotation updates Secret Manager and then triggers a controlled redeployment of the current
image. The old credential remains valid until the replacement container passes its startup check.

Alerts should cover bot process absence, sustained marking retries, assignment delivery failures,
Cloud SQL capacity, backup failures, and media-deletion failures. The existing pilot runbook
remains the authority for student privacy, provider disclosure, review, and incident handling.
