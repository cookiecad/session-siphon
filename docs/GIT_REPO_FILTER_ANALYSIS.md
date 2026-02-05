# Git Repo Filter Analysis

## Objective
Add a "Git Repo" filter to the conversation search UI to allow users to narrow down AI sessions by the repository they were working in.

## Impact Analysis

### 1. Data Model Changes
The internal data models need to be updated to carry the `git_repo` metadata.

**File:** `src/session_siphon/models.py`
- Update `CanonicalMessage` dataclass:
  ```python
  @dataclass
  class CanonicalMessage:
      ...
      git_repo: str | None = None  # New field
      ...
  ```
- Update `CanonicalMessage.to_typesense_doc()` to include `git_repo`.
- Update `Conversation` dataclass and its `to_typesense_doc()` method similarly.

**File:** `src/session_siphon/processor/indexer.py`
- Update `MESSAGES_SCHEMA` and `CONVERSATIONS_SCHEMA`:
  ```python
  {"name": "git_repo", "type": "string", "facet": True, "optional": True}
  ```
  Note: `optional: True` is important for backward compatibility if we don't backfill immediately.

### 2. Git Repository Extraction Logic
We need a robust way to determine the git info from a `project` path.

**Proposed Logic:**
Use a utility function that takes a path and determines if it's inside a git repo.
- **Input:** `project` path (string)
- **Mechanism:** Run `git -C <project_path> remote get-url origin`
- **Output:** The remote URL (e.g., `git@github.com:owner/repo.git`) or the directory name if no remote exists but it is a git repo.
- **Normalization:** Strip `.git` suffix, maybe just use `owner/repo` format for cleaner UI filtering.

**Implementation Location:**
A new utility module `src/session_siphon/processor/git_utils.py` is recommended to keep `parsers` clean.

### 3. Parser Updates
Update existing parsers to utilize the extraction logic.

**File:** `src/session_siphon/processor/parsers/vscode.py` (and others)
- In `parse()`, after extracting `project` path:
  ```python
  git_repo = get_git_repo_info(project)
  ```
- Pass this `git_repo` to the `CanonicalMessage` constructor.

### 4. Migration Strategy (Re-indexing)
The user noted: "we will need to reindex all the conversations".
We have two options:

**Option A: Full Re-ingest (Resend from sources)**
- **Pros:** Cleanest state.
- **Cons:** Slow; requires access to all original source files (which might have been archived or deleted from the inbox).
- **Feasibility:** Only possible if the original source files are still in the `archive/` folder or can be re-exported from the tools.

**Option B: In-place Update (Recommended)**
Since we already store the `project` path in Typesense, we can run a migration script.
- **Mechanism:**
  1. Query all `conversations` from Typesense.
  2. For each conversation, extract the `project` path.
  3. Run the "Git Repository Extraction Logic" locally on the machine.
  4. Update the Typesense document with the new `git_repo` field.
- **Pros:** Very fast; non-destructive.
- **Cons:** Requires the `project` paths to still exist on the local machine (which is true for a local dev tool).

### 5. Frontend/UI (Future Work)
- Update `src/lib/typesense.ts` to include `git_repo` in search parameters.
- Add a new `SearchableSelect` or Facet component for "Git Repo".

## Recommendation
1. Update Data Models and Schemas first.
2. Implement `git_utils.py`.
3. Update Parsers to start capturing this for *new* data.
4. Write a temporary migration script (Option B) to backfill existing Typesense records.
