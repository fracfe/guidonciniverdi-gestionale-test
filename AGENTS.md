# AGENTS.md — Guidoncini Verdi GV-TEST development workspace

## Project purpose

This workspace contains the development and test environment for the Guidoncini Verdi platform.

The platform is composed of two independent Git repositories that work together:

* `guidonciniverdi-gestionale-test`
* `guidonciniverdi-wordpress-test`

The purpose of GV-TEST is to develop and verify the complete platform without affecting production systems.

Development must remain reproducible and portable so that the same logical application stack can be tested on GV-TEST and later deployed on another Linux/Docker host through configuration changes rather than source-code changes.

---

# Current development model

Development is performed from VS Code on the developer workstation using Remote SSH to the GV-TEST virtual machine.

The workstation acts primarily as the user interface.

The files being edited, Git repositories, Docker environment, application processes and integration-test environment are located on GV-TEST.

Therefore, when Codex is running in the VS Code Remote SSH workspace, GV-TEST is the active development and test environment.

Codex may inspect, modify and test files directly on GV-TEST, subject to all safety and Git rules in this document.

Production remains completely outside the allowed development boundary.

---

# GV-TEST workspace

The main workspace is:

`/opt/gv-test`

Relevant Git repositories are:

* `/opt/gv-test/gestionale`
* `/opt/gv-test/wordpress`

These are independent repositories.

`/opt/gv-test` itself must not be assumed to be a Git repository.

Before performing Git operations, always identify the repository root using:

`git rev-parse --show-toplevel`

and verify:

`git status`

`git branch --show-current`

Never assume that a Git command executed from one repository affects the other.

---

# Repository structure

## Gestionale repository

Repository path on GV-TEST:

`/opt/gv-test/gestionale`

Fork:

`fracfe/guidonciniverdi-gestionale-test`

Upstream:

`egit-guidoncini-verdi/guidonciniverdi-gestionale`

Development base branch:

`dev`

Normal development for this test fork is based on `dev`.

The repository contains several components, including:

* `gestionale/`

  * Flask web application
  * SQLAlchemy ORM
  * Flask-Login
  * administrative and user interfaces
  * registrations management
  * reports
  * database initialization
  * Flask CLI commands

* `gestionale-daemon/`

  * asynchronous/background jobs
  * WordPress REST API integration
  * mail queue
  * Telegram queue
  * scheduled notifications

* `infra/`

  * infrastructure/deployment-related files belonging to this Git repository

* `scripts/`

  * project scripts and operational helpers

* `shared/`

  * code or resources shared by project components

* `static/`

  * static project resources

The application supports Docker deployment.

MariaDB is used as the persistent application database in the intended deployment.

### Important `infra` rule

The Gestionale Git repository contains its own versioned `infra/` directory.

Do not assume that another directory named `infra` elsewhere under `/opt/gv-test` is automatically the same directory or is part of the same Git repository.

Before modifying infrastructure files, verify their ownership with:

`git rev-parse --show-toplevel`

and:

`git status`

Only modify the versioned file that actually belongs to the intended repository.

---

## WordPress repository

Repository path on GV-TEST:

`/opt/gv-test/wordpress`

Fork:

`fracfe/guidonciniverdi-wordpress-test`

Upstream:

`egit-guidoncini-verdi/guidonciniverdi-wordpress`

Current development base branch:

`main`

The upstream repository currently does not use the same `dev` workflow as the Gestionale repository.

The repository contains the WordPress development code and Guidoncini Verdi-specific components, including:

* Guidoncini Verdi WordPress theme
* Guidoncini Verdi plugin
* Guidoncini Verdi Gutenberg blocks plugin
* frontend tooling
* Docker/development configuration where provided by the repository

The Guidoncini Verdi plugin implements application-specific functionality including:

* custom post type `navigazione`
* REST API behaviour
* squadriglia/user restrictions
* custom taxonomies
* Guidoncini Verdi specialità
* application metadata
* WordPress roles and capabilities behaviour

---

# System architecture

The logical integration is approximately:

```text
Gestionale Flask
       |
       v
Gestionale MariaDB
       ^
       |
Gestionale Daemon
       |
       | WordPress REST API
       v
WordPress
       |
       v
WordPress Database
```

The Gestionale and Gestionale Daemon share the application database according to the existing project architecture.

The daemon processes asynchronous operations and communicates with WordPress through its REST API.

GV-TEST is intended to run the complete integration environment using test services and test data.

---

# GV-TEST responsibilities

GV-TEST is the active development and integration environment.

It may contain services such as:

* Gestionale Flask
* Gestionale daemon
* Gestionale MariaDB
* WordPress
* WordPress database
* Guidoncini Verdi theme
* Guidoncini Verdi plugin
* Guidoncini Verdi Gutenberg blocks
* test SMTP service
* optional reverse proxy
* supporting Docker services required by the stack

GV-TEST must use only test data and test credentials.

Codex may work directly with these services when necessary to complete and verify a development task.

---

# CRITICAL PRODUCTION SAFETY RULES

Production systems MUST NEVER be used for development or automated tests.

Do not perform development or automated write requests against:

* `https://guidonciniverdi.it`
* its production WordPress REST API
* the production WordPress database
* the production Gestionale database
* production SMTP servers
* production Telegram bots
* any other production service or datastore

Never use real production passwords, application passwords, tokens, API credentials or database credentials in development files.

Never commit secrets to Git.

Any code path capable of:

* creating WordPress users
* creating or editing WordPress posts
* deleting WordPress users or posts
* sending email
* sending Telegram messages
* changing application databases
* executing database migrations
* modifying external services

must be verified to target GV-TEST before execution.

If environment configuration is uncertain, STOP rather than defaulting to production.

Production URLs must never be used as fallback or default values for test execution.

A value being present in existing upstream code does not make it safe for GV-TEST.

---

# Known production references in current code

The current/upstream code may contain hardcoded references to:

`guidonciniverdi.it`

including references in generated content or notification messages.

Treat these as legacy or production-specific values.

Do not assume that every current hardcoded URL is suitable for the test environment.

Prefer environment configuration for values that change between environments.

Where practical, future refactoring should separate:

* application logic
* environment configuration
* production-specific URLs
* notification destinations
* external service credentials

Do not broaden the scope of a task solely to perform this refactoring unless it is required by the requested change.

---

# WordPress integration

The Gestionale daemon communicates with WordPress through the REST API.

The WordPress base URL is provided through:

`WORDPRESS_URL`

On GV-TEST it must resolve to the GV-TEST WordPress instance.

Never use the production WordPress URL for integration testing.

Related configuration includes:

* `WORDPRESS_USER`
* `WORDPRESS_PASSWORD`

Use dedicated test credentials.

The daemon may interact with resources such as:

* WordPress users
* posts
* categories
* specialità
* application metadata

The WordPress plugin provides application-specific REST behaviour required by this integration.

Before exercising a write-capable integration test, verify the effective value of `WORDPRESS_URL`.

Do not rely only on assumptions derived from source code or `.env.example` files.

---

# Gestionale environment variables

Relevant application configuration includes values such as:

* `DB_TYPE`
* `DB_USER`
* `DB_PASSWORD`
* `DB_HOST`
* `DB_PORT`
* `DB_NAME`
* `SECRET_KEY`

Daemon configuration additionally includes values such as:

* `MAIL_USERNAME`
* `MAIL_HOST`
* `MAIL_PORT`
* `WORDPRESS_URL`
* `WORDPRESS_USER`
* `WORDPRESS_PASSWORD`
* `TELEGRAM_TOKEN`

Never hardcode real secrets.

Prefer environment injection, `.env` files excluded from Git, Docker secrets or the configuration mechanism already established by the project.

Do not print secret values unnecessarily in logs, reports or terminal output.

---

# Database

The main deployment target uses MariaDB.

The Gestionale accesses its database through SQLAlchemy.

Database schema changes must follow the migration mechanism already used by the project.

Do not manually change production schemas.

For a schema change on GV-TEST:

1. inspect the existing models;
2. inspect existing migrations;
3. determine the correct migration path;
4. create the required migration;
5. inspect the generated migration before executing it;
6. verify the database target is GV-TEST;
7. test migration from the previous schema;
8. verify application startup;
9. verify the affected functionality.

Do not treat a schema change as complete if only the ORM model was modified.

Never run destructive migration commands without first understanding their effect on the GV-TEST database.

---

# Gestionale initialization

The project exposes Flask CLI commands including:

`flask init_db`

for initialization of application data.

Other project commands may include:

`flask crea_regione <nome>`

and:

`flask aggiorna_anno <anno>`

Before executing application CLI commands, identify:

* the container or environment in which they must run;
* the effective database target;
* whether the command changes persistent data.

During development, these commands may be executed against GV-TEST when required by the task.

They must never target production.

---

# WordPress frontend development

The WordPress project uses frontend tooling including Tailwind CSS.

Relevant scripts may include:

`npm run dev`

`npm run build`

`npm run start-sync-server`

Use the scripts and working directory defined by the repository.

Do not commit generated dependency directories or build artefacts unless they are intentionally tracked by the project.

Before adding generated files, inspect the repository's existing `.gitignore` and tracking conventions.

---

# Git workflow

There are two independent Git repositories.

Never assume that a commit in one repository includes changes from the other.

## Remotes

For the development forks:

`origin`

points to Francesco's development fork.

`upstream`

points to the official `egit-guidoncini-verdi` repository.

Normal development pushes, when explicitly requested, go to `origin`.

Do not push to `upstream`.

Do not modify upstream branches directly.

---

# Mandatory Git checks before changes

Before modifying files in a repository, Codex must verify:

`git rev-parse --show-toplevel`

`git branch --show-current`

`git status`

If the working tree already contains unrelated modifications:

* do not discard them;
* do not overwrite them;
* identify them;
* preserve them;
* report them before making changes that could interfere with them.

Never run destructive Git commands such as:

* `git reset --hard`
* `git clean -fd`
* `git restore <file>`

against user work unless explicitly requested and the consequences are understood.

---

# Gestionale branch workflow

Base integration branch:

`dev`

Substantial features should normally use dedicated branches such as:

* `feature/<short-description>`
* `fix/<short-description>`
* `refactor/<short-description>`

Branches normally start from `dev`.

Typical workflow:

```text
git switch dev
git pull --ff-only origin dev
git switch -c feature/example
```

Do not create branches automatically when the user has not asked for it if the current workflow intentionally uses `dev`.

Do not switch branches while uncommitted work exists unless it is known to be safe.

Do not automatically commit, push, merge or rebase unless explicitly requested.

---

# WordPress branch workflow

Current fork development base:

`main`

The WordPress repository currently follows a different branch structure from the Gestionale repository.

For substantial isolated changes, prefer dedicated branches such as:

* `feature/<short-description>`
* `fix/<short-description>`
* `refactor/<short-description>`

Do not introduce a new `dev` branch merely because the Gestionale repository uses one.

Creating or changing the WordPress branch strategy is a separate repository-management decision and must be explicit.

Do not automatically commit, push, merge or rebase unless explicitly requested.

---

# Upstream synchronization

Upstream repositories are read-only references for this development workspace.

Before incorporating upstream changes:

1. fetch upstream;
2. inspect the changes;
3. identify the current local divergence;
4. determine whether upstream changes conflict with local development;
5. merge or rebase deliberately;
6. run relevant tests again.

Do not automatically overwrite local work with upstream branches.

Do not assume that `origin` and `upstream` have identical histories.

---

# Codex operating model

Codex is expected to operate directly inside the GV-TEST Remote SSH workspace.

Before changing code:

1. identify which repository owns the functionality;
2. verify the repository root;
3. verify Git branch and working tree state;
4. inspect the relevant existing implementation;
5. understand the integration boundary between Gestionale and WordPress;
6. determine whether the change affects:

   * database schema;
   * REST API;
   * Docker configuration;
   * background jobs;
   * email;
   * Telegram;
   * authentication or permissions;
7. identify the minimum set of files/components that needs to change.

Prefer small and understandable changes over large rewrites.

Do not rewrite existing architecture solely for stylistic reasons.

Preserve compatibility with the existing project unless the requested task explicitly requires an architectural change.

When discovering a bug unrelated to the requested task, report it before modifying unrelated code.

Do not make unrelated cleanup changes silently.

---

# Codex execution permissions on GV-TEST

When running through VS Code Remote SSH on GV-TEST, Codex may, when necessary for the requested task:

* inspect files;
* edit files;
* inspect Git history and diffs;
* run syntax checks;
* run unit tests;
* run application tests;
* inspect Docker configuration;
* inspect running test containers;
* read GV-TEST logs;
* run non-destructive diagnostic commands;
* execute `curl` or equivalent requests against GV-TEST services;
* execute test-only Flask commands;
* rebuild or restart GV-TEST containers when required to test the requested change;
* perform integration tests between the Gestionale and WordPress test services;
* inspect GV-TEST database state when necessary to diagnose or verify behaviour.

Before any command with persistent or destructive effects, verify the target and understand the expected impact.

Codex must not interpret access to the VM as permission to make arbitrary infrastructure changes unrelated to the requested task.

---

# Operations requiring explicit user request

Do not automatically:

* commit;
* push;
* merge;
* rebase shared branches;
* delete Git branches;
* modify upstream repositories;
* deploy to production;
* access production systems;
* run production migrations;
* alter production databases;
* use production credentials;
* send real production email;
* send messages through production Telegram bots.

Repository changes should remain uncommitted until the user explicitly asks for a commit or push.

---

# Verification levels

Because Codex now operates directly on GV-TEST, local code verification and integration verification may occur in the same Remote SSH workspace.

Still distinguish clearly between different verification levels.

## Code-level verification

Examples:

* code inspection
* syntax checks
* static analysis
* unit tests
* template validation
* isolated application tests

## Service-level verification

Examples:

* Flask application starts correctly
* affected container starts correctly
* endpoint responds as expected
* logs show no new relevant errors
* database query/migration behaves correctly

## Integration verification

Examples:

* Gestionale communicates correctly with the daemon
* daemon communicates correctly with WordPress
* expected WordPress user/content is created
* background job reaches the correct state
* email is captured by the GV-TEST mail service
* end-to-end registration/provisioning flow works

Never report a higher verification level than was actually performed.

Passing a syntax check is not equivalent to verifying the running application.

Passing a unit test is not equivalent to verifying the full WordPress integration.

---

# Cross-repository changes

Some features may require coordinated changes in both repositories.

Examples include:

* new WordPress metadata
* REST API changes
* new custom post types
* authentication changes
* provisioning behaviour
* changes to generated Diario di Bordo content
* changes to shared contracts between Gestionale and WordPress

When a feature spans both repositories:

1. describe the interface or contract change;
2. identify which repository owns each side;
3. modify only the required files;
4. keep Git operations separate;
5. test the two sides together on GV-TEST;
6. consider deployment order and backward compatibility.

Never assume both repositories are on the same branch or commit.

Never run one `git add`, commit or push assuming it covers both repositories.

At the end, report Git state separately for each affected repository.

---

# Test environment principles

GV-TEST should mimic the production architecture closely enough to provide meaningful integration testing without using production data or credentials.

Prefer Docker service discovery and explicit test configuration.

Where appropriate, services should communicate using Docker service names rather than fixed host addresses.

The effective runtime configuration is authoritative.

Do not assume an example value such as:

`http://wordpress/wp-json/wp/v2`

is correct until the actual GV-TEST Compose/network configuration has been inspected.

The test database should be treated as test data, but persistent or destructive operations must still be intentional.

Email must use a test destination or local capture service.

Telegram must be disabled or use an explicitly dedicated test bot.

External side effects should be disabled by default wherever practical.

---

# End-to-end acceptance test

A major integration change should be considered fully verified only when the relevant complete workflow succeeds on GV-TEST.

The target registration/provisioning workflow includes:

1. initialize or prepare the Gestionale test database;
2. create/configure a test region if required;
3. open registrations;
4. submit a test squadriglia registration;
5. review the registration in the Gestionale;
6. authorize the registration;
7. generate the WordPress job;
8. daemon processes the job;
9. WordPress test user is created with the expected role and capabilities;
10. required WordPress content is created;
11. categories, specialità and metadata are correctly assigned where applicable;
12. registration reaches the expected final state;
13. generated email appears in the GV-TEST test mailbox where applicable;
14. test squadriglia can log in to WordPress where applicable;
15. permissions and content visibility behave as expected.

Not every task requires this complete acceptance test.

Run only the portions relevant to the requested change unless full end-to-end verification is required.

No step may contact production.

---

# Docker and portability

Keep the application portable.

Avoid introducing unnecessary assumptions about:

* fixed host IP addresses
* Proxmox-specific filesystem paths inside application logic
* provider-specific paths
* Windows-specific paths inside Linux containers
* production domain names
* one specific test host

Prefer:

* Docker service discovery
* environment variables
* named volumes
* explicit configuration
* reproducible Compose definitions
* environment-specific configuration outside application logic

The same logical stack should eventually be runnable on:

* GV-TEST
* another Linux/Docker test host
* a remote Linux/Docker production host

through configuration differences rather than source-code rewrites.

GV-TEST-specific operational files may exist where appropriate, but application code should not become unnecessarily coupled to `/opt/gv-test`.

---

# Observable workflow states

For asynchronous processes, the Gestionale should make the actual backend state visible and understandable to the operator.

Principle:

Every important asynchronous operation should expose a user-readable state describing what is actually happening instead of forcing the operator to infer the state from indirect effects.

For WordPress provisioning of squadriglie, prefer explicit states such as:

* Da abilitare
* Abilitazione in corso
* Abilitata
* Errore creazione utente
* Errore creazione pagina

Where useful and supported by the backend, the Gestionale should expose information such as:

* last update;
* related `JobWordpress` state;
* presence of the WordPress user;
* presence of the WordPress page or post.

Displayed information must derive from real backend state rather than frontend assumptions.

Do not hide meaningful technical failures behind misleading generic success states.

The objective is that an operator can understand the state of a squadriglia without having to inspect databases, WordPress or application logs directly.

---

# Definition of done

A change is complete, where applicable, when:

* the requested behaviour is implemented;
* the code remains understandable;
* no unrelated modifications were silently introduced;
* no secrets were introduced;
* production endpoints were not used;
* database migrations are included when required;
* Docker configuration still works where affected;
* the relevant GV-TEST services start correctly;
* relevant code-level tests pass;
* relevant service-level tests pass;
* relevant integration tests pass;
* integration with the other repository still works where affected;
* documentation or configuration examples are updated when behaviour changed;
* Git changes are limited to intended repositories and files;
* asynchronous operations expose clear and truthful state where applicable.

A task is not fully verified merely because code was edited successfully.

Anything not tested must be explicitly reported as unverified.

---

# Handoff and feedback after every modification

After every task that modifies code, configuration or tests, provide a concise but complete report.

The report must include:

* task objective;
* problem/root cause identified;
* repository or repositories affected;
* files modified;
* changes made;
* relevant technical decisions;
* tests and checks executed;
* results of those tests;
* anything still unverified;
* known risks or open problems;
* whether any container/service was rebuilt or restarted;
* Git branch and working-tree state;
* any further command the user still needs to execute.

If assumptions were necessary, state them explicitly.

If something could not be verified, do not describe it as solved.

Do not modify code unrelated to the task without reporting it.

Before making a broad architectural change or touching multiple components beyond what is clearly required by the task, explain why the broader change is necessary before proceeding.

The final report should be understandable by another technician or AI without requiring hidden context.

---

# Git handoff after changes

Before starting work:

* verify repository root;
* verify current branch;
* run `git status`.

After modifying files:

* run `git status`;
* run `git diff --stat`;
* inspect the relevant `git diff`;
* summarize the actual diff.

Do not automatically commit or push.

If both repositories were modified, perform and report these checks separately for:

* `/opt/gv-test/gestionale`
* `/opt/gv-test/wordpress`

Never discard pre-existing user changes merely to obtain a clean working tree.

---

# Final safety principle

GV-TEST is intentionally available for development, experimentation and integration testing.

Production is not.

When choosing between:

* a test endpoint and a production endpoint;
* test credentials and production credentials;
* a reversible GV-TEST operation and an uncontrolled external side effect;

always choose the test-safe path.

If the target cannot be established with confidence, stop the potentially destructive or externally visible operation and report what must be verified.
