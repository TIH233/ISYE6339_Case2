--- 
This serves for user's suggestions on the design of the skill
Do not make large changes to the skills unless user feedback in the conversation
--- 

# Architectural Suggestions for Code Realization

These are the structural guidelines and operational boundaries for generating code in this project. The goal is to maintain a readable, mathematically sound, and cleanly version-controlled pipeline.

## 1. Data Handling Philosophy
To balance computational speed with readability, strictly separate the data processing layers:
* **Computation & Simulation:** Default to `numpy` for all heavy numerical lifting, matrix manipulations, and mathematical solver inputs. 
* **Visualization & Snapshots:** Use `pandas` exclusively for state summaries, final outputs, and human-readable pipeline checkpoints. 
* **Integrity:** Do not mix `numpy` arrays and `pandas` DataFrames within the same active data structure. Explicitly convert between them only at the boundaries of computational steps.
* **Domain Libraries:** Utilize specialized GIS and OR optimization libraries as dictated by the theoretical model.

## 2. Object-Oriented Design
Keep OOP implementations practical and grounded in the physical reality of the network. 
* Design classes that represent tangible components (e.g., `Node`, `Link`, `NetworkManager`) rather than overly abstract architectures. 
* The primary goal of the OOP structure is human readability and logical grouping of attributes, making it easy to review the physical constraints of the network.

## 3. Pipeline State Management
Avoid recomputing heavy operations during pipeline execution in the `.ipynb` files.
* Whenever a computationally expensive object (e.g., a solved network state, a massive distance matrix) is generated, serialize and save it to permanent storage immediately.
* Use appropriate formats: `.npy` for raw arrays, or `joblib`/`pickle` for complex class instances and solver states.
* Subsequent pipeline steps should attempt to load these objects from disk before running the computation.

## 4. Documentation and Mathematical Grounding
Code documentation must bridge the gap between the theoretical model and the Python implementation.
* In the `.ipynb` files, precede complex execution cells with a Markdown cell.
* Use LaTeX to write out the governing equations or constraints for that specific step (e.g., $\sum_{i \in I} x_{ij} = d_j$). This ensures the code directly maps to the retrieved `Task.md` theory.
* Use standard, concise docstrings for `.py` script functions.

## 5. Version Control Protocol (Stage Completion)
Maintain a clean project history by treating version control as a standard step after every successful milestone.
* Upon successfully completing a subtask and passing all associated sanity checks, **pause execution**.
* Present a brief summary of the completed task to the user and request explicit consent to commit the progress.
* Once consent is granted, utilize the provided terminal tools (e.g., executing `./git_tools.sh sync` via Zsh) to stage, commit, and push the working directory to the remote repository.

## 6. Fault Tolerance and Rollback
Network design simulations may run without standard syntax errors but produce physically impossible data (e.g., negative flows or violated capacity limits).
* If a sanity check fails due to illogical data bounds, **do not attempt to force the pipeline forward.**
* **Rollback Mechanism:** Execute a hard reset to the last known working state using standard Git commands (e.g., `git reset --hard HEAD` to drop uncommitted breaking changes) to ensure the environment is uncontaminated.
* **Issue Reporting:** Upon rolling back, generate an `Issue_Report.md` in the project root using the following schema to flag the anomaly for human review.

### Issue Report Schema
```yaml
Issue: [Subtask Index / Name]
Timestamp: [Date/Time]
Failure Point: [Specific notebook cell or function]
Expected Bound: [Theoretical constraint from Task.md, e.g., Total Flow == 5000]
Actual Output: [The erroneous data result, e.g., Total Flow == -250]
Action Taken: Codebase rolled back to previous stable state. Awaiting human review.


### 2. The Git Tools Script (`git_tools.sh`)

To keep the Coder agent from wasting time writing out raw Git commands for standard syncs, you can provide this executable shell script. Since you are operating in a standard terminal environment (like Zsh), the agent can simply call `./git_tools.sh commit "message"` or `./git_tools.sh sync`.

```bash
#!/usr/bin/env zsh

# A simple wrapper for standard Git operations

COMMAND=$1
MSG=$2

case "$COMMAND" in
    "status")
        echo "Checking repository status..."
        git status -s
        ;;
    "commit")
        if [ -z "$MSG" ]; then
            echo "Error: Please provide a commit message."
            echo "Usage: ./git_tools.sh commit 'Your message here'"
            exit 1
        fi
        echo "Adding all changes and committing..."
        git add .
        git commit -m "$MSG"
        ;;
    "pull")
        echo "Pulling latest changes from remote..."
        git pull origin main
        ;;
    "sync")
        echo "Executing full sync (Pull -> Add -> Commit -> Push)..."
        if [ -z "$MSG" ]; then
            MSG="Auto-sync update"
        fi
        git pull origin main
        git add .
        git commit -m "$MSG"
        git push origin main
        echo "Sync complete."
        ;;
    *)
        echo "Usage: ./git_tools.sh {status|commit|pull|sync} ['commit message']"
        exit 1
        ;;
esac