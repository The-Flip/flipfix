# AI Assistant Workflow Guide

This guide documents patterns for working effectively with AI assistants (like Claude Code) on this project.

## Branch Management in Long AI Sessions

**Problem:** AI assistants maintain context across a long conversation. If you merge a PR mid-session and continue working, the AI will keep committing to the same branch, causing merge conflicts when you try to create the next PR.

**Solution:** Start a fresh branch after each PR merge, even in the same AI session.

### When a PR Gets Merged Mid-Session

After you merge a PR, explicitly tell the AI to start a new branch:

```
"The PR was merged. Switch to main, pull latest, and create a new branch called feature/next-thing"
```

Or simply:

```
"Start a fresh branch from main for the next task"
```

### The AI Will Do This Automatically

The AI should:
1. Switch to main: `git checkout main`
2. Pull latest: `git pull origin main`
3. Create new branch: `git checkout -b feature/descriptive-name`

This ensures the new branch starts from the latest main (including the just-merged PR) rather than continuing on the old feature branch.
