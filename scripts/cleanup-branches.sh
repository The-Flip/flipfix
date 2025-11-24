#!/bin/bash

# Interactive script to clean up local and remote Git branches
# that have been merged or deleted on GitHub

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Fetching latest from GitHub...${NC}"
git fetch --prune origin

echo ""
echo -e "${BLUE}Finding branches safe to delete...${NC}"
echo ""

# Arrays to store branches
declare -a gone_branches
declare -a merged_branches

# Get current branch to avoid deleting it
current_branch=$(git branch --show-current)

# Find branches whose remote has been deleted (marked as "gone")
while IFS= read -r line; do
    # Remove leading asterisk and whitespace, then get first field
    branch=$(echo "$line" | sed 's/^[* ]*//' | awk '{print $1}')

    # Skip main, master, current branch, and empty strings
    if [[ -n "$branch" && "$branch" != "main" && "$branch" != "master" && "$branch" != "$current_branch" ]]; then
        gone_branches+=("$branch")
    fi
done < <(git branch -vv | grep ': gone]')

# Find branches that have been merged into main but remote still exists
while IFS= read -r line; do
    # Remove leading asterisk and whitespace, then get first field
    branch=$(echo "$line" | sed 's/^[* ]*//' | awk '{print $1}')

    # Skip main, master, current branch, empty strings, and branches already in gone list
    if [[ -n "$branch" && "$branch" != "main" && "$branch" != "master" && "$branch" != "$current_branch" ]]; then
        # Check if not already in gone_branches
        is_gone=0
        for gone in "${gone_branches[@]}"; do
            if [[ "$gone" == "$branch" ]]; then
                is_gone=1
                break
            fi
        done

        if [[ $is_gone -eq 0 ]]; then
            merged_branches+=("$branch")
        fi
    fi
done < <(git branch --merged main | grep -v '^\*')

# Check if there are any branches to delete
total_count=$((${#gone_branches[@]} + ${#merged_branches[@]}))

if [[ $total_count -eq 0 ]]; then
    echo -e "${GREEN}No branches to clean up! 🎉${NC}"
    exit 0
fi

# Display branches
echo -e "${YELLOW}Found $total_count branch(es) safe to delete:${NC}"
echo ""

if [[ ${#gone_branches[@]} -gt 0 ]]; then
    echo -e "${RED}Deleted on GitHub:${NC}"
    for branch in "${gone_branches[@]}"; do
        echo "  - $branch"
    done
    echo ""
fi

if [[ ${#merged_branches[@]} -gt 0 ]]; then
    echo -e "${GREEN}Merged into main:${NC}"
    for branch in "${merged_branches[@]}"; do
        echo "  - $branch"
    done
    echo ""
fi

# Ask for confirmation
echo -e "${YELLOW}Delete these branches locally and on GitHub? [Y/n]${NC} "
read -r response

# Default to Yes if just Enter is pressed
if [[ -z "$response" ]] || [[ "$response" =~ ^[Yy]$ ]]; then
    echo ""
    echo -e "${BLUE}Deleting branches...${NC}"

    deleted_count=0
    error_count=0

    # Delete gone branches (local only, remote already gone)
    for branch in "${gone_branches[@]}"; do
        echo -n "  Deleting local branch: $branch... "
        if git branch -D "$branch" > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC}"
            ((deleted_count++))
        else
            echo -e "${RED}✗${NC}"
            ((error_count++))
        fi
    done

    # Delete merged branches (both local and remote)
    for branch in "${merged_branches[@]}"; do
        echo -n "  Deleting local branch: $branch... "
        if git branch -d "$branch" > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC}"
            ((deleted_count++))

            # Try to delete remote branch if it exists
            echo -n "  Deleting remote branch: $branch... "
            if git push origin --delete "$branch" > /dev/null 2>&1; then
                echo -e "${GREEN}✓${NC}"
            else
                echo -e "${YELLOW}(not found or already deleted)${NC}"
            fi
        else
            echo -e "${RED}✗${NC}"
            ((error_count++))
        fi
    done

    echo ""
    echo -e "${GREEN}Done! Deleted $deleted_count branch(es).${NC}"

    if [[ $error_count -gt 0 ]]; then
        echo -e "${RED}Failed to delete $error_count branch(es).${NC}"
    fi
else
    echo -e "${YELLOW}Cancelled. No branches were deleted.${NC}"
fi
