AI assistant rules live in `docs/README.md`. Read that file before answering questions or making changes. That guide spells out how AI assistants are to work with HTML, CSS, Django/Python, the project structure, data model, and tests.

## Branch Management After PR Creation

**IMPORTANT:** After creating a PR and providing the PR link to the user, you MUST ask:

```
"Let me know when the PR is merged so I can start a fresh branch for any additional work."
```

**Why:** If a PR merges mid-session and work continues on the same branch, it causes merge conflicts when creating the next PR. Git branches are designed to be short-lived and deleted after merge.

**If the user says the PR was merged:**
1. Switch to main: `git checkout main`
2. Pull latest: `git pull origin main`
3. Create new branch: `git checkout -b feature/descriptive-name`

See `docs/AI_Workflow.md` for full details.
