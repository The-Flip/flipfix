---
description: Run comprehensive pre-PR quality checklist for Flipfix
---

# Pre-PR Quality Checklist

You are helping the user prepare code for a pull request by guiding them through a comprehensive quality checklist.

## Your Role

Guide the user through each step of the checklist systematically. For each step:
1. Explain what needs to be done
2. Execute the required checks/commands
3. Report the results clearly
4. Only proceed to the next step after current step passes or user acknowledges issues

## Checklist Steps

### 1. Issue Compliance Verification (CRITICAL - Do This First!)
- Ask the user for the GitHub issue number they're working on (if applicable)
- Use `gh issue view <number>` to fetch the issue details
- Review ALL requirements in the issue
- Verify 100% completion of specified requirements
- If any requirement cannot be met, STOP and discuss with user before proceeding

### 2. Code Quality Foundation

**Run Quality Checks:**
- Run `make quality` (format + lint + typecheck)
- Report any files that were modified or errors found
- If errors, STOP and require fixes before proceeding

**Documentation Check:**
- Review the project docs referenced in CLAUDE.md:
  - `docs/HTML_CSS.md` for templates/CSS
  - `docs/Forms.md` for form patterns
  - `docs/Datamodel.md` for models
  - `docs/Testing.md` for test patterns
  - `docs/Django_Python.md` for Django conventions
- Flag any code that doesn't follow documented patterns

### 3. Architecture and Implementation Review

**Antipattern Scan:**
- Use the Task tool with subagent_type="antipattern-scanner" on all new/modified code
- Look for: SRP violations, dependency inversion failures, naming issues
- Report findings and wait for user to address before continuing

**Clean Code Review:**
- Use the Task tool with subagent_type="clean-code-reviewer" on all new/modified code
- Check: single responsibility, meaningful names, small functions, DRY violations
- Report findings and wait for user to address before continuing

**Code Smell Detection:**
- Use the Task tool with subagent_type="code-smell-detector" on all new/modified code
- Identify maintainability hints and readability improvements
- Report findings for user consideration

### 4. Test Quality Validation

**Test Implementation Audit:**
- Scan ALL test files for:
  - Partially implemented tests (just `pass` statements)
  - Placeholder implementations
  - Tests that don't follow patterns in `docs/Testing.md`
- Flag any tests that use fake implementations without justification
- Check that tests use Django's TestCase as documented

**Run Tests:**
- Run `make test` to execute test suite
- Report pass/fail status
- If failures exist, STOP and require fixes before proceeding

### 5. Final Verification

**Pre-commit Hooks:**
- Run `make precommit` to verify all pre-commit hooks pass
- Report any violations
- Require fixes before proceeding

## Success Criteria

All steps must pass before PR creation:
- All issue requirements completed (if applicable)
- `make quality` passes (format + lint + typecheck)
- Code follows documented patterns
- No critical antipatterns detected (or acknowledged/fixed)
- Clean code review passed (or issues addressed)
- All tests passing (`make test`)
- Pre-commit hooks pass (`make precommit`)

## Final Output

After completing all steps, provide:
1. Summary of checklist completion status
2. List of any remaining concerns or warnings
3. Confirmation that code is ready for PR, OR list of items that need attention

## Important Notes

- **Fail Fast**: Stop at first major issue - don't continue if critical problems exist
- **Follow the Docs**: All code should follow patterns in `docs/` directory
- **Issue Compliance**: 100% requirement completion is mandatory when working on an issue
