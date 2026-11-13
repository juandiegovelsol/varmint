"""Where the bundle and its runs live on disk - the one place that decides it.

Two task layouts are legal, and nothing may depend on the task folder's NAME:

    flat      <root>/Tasks/task.toml
    nested    <root>/Tasks/<any-task-name>/task.toml

In both, the run folders (Oracle/, Nop/, Trials/, ...) are siblings of Tasks/ under <root>.

Run folders also come in two shapes, and the trial dir's name is never assumed either (harbor
names it `<task-folder-name>__<rand>`, so a nested task is not `Tasks__*`):

    <root>/Oracle/<trial>/verifier/...            mm_run.sh: the job dir IS Oracle/
    <root>/Oracle/<job-timestamp>/<trial>/...     a job harbor named itself, one level down

Trials/ holds the trial's two phases side by side, as the delivery template does, and only
with_images/ is the trial run the checks read (see run_path):

    <root>/Trials/with_images/<trial>/...         normal attempts
    <root>/Trials/without_images/<trial>/...      text-only attempts, images stripped

Stdlib only, no imports from the rest of checks/, so every check and fix.py can use it without
an import cycle.
"""
import os

TASKS_DIR_NAMES = ("Tasks", "tasks")


class AmbiguousLayout(Exception):
    """More than one task under one Tasks/ - the caller must point at the one it means."""

    def __init__(self, container, names):
        self.container, self.names = container, names
        super().__init__(
            f"{container} holds {len(names)} tasks ({', '.join(names)}) - point at one of them, "
            f"e.g. {os.path.join(container, names[0])}")


def _task_children(container):
    try:
        names = sorted(os.listdir(container))
    except OSError:
        return []
    return [n for n in names if os.path.isfile(os.path.join(container, n, "task.toml"))]


def find_task_dir(path):
    """The directory holding task.toml, or None. Accepts the task dir itself, a Tasks/ dir in
    either layout, or the deliverables root above it. Raises AmbiguousLayout when a Tasks/ holds
    several tasks, rather than silently auditing whichever sorts first."""
    path = os.path.abspath(path)
    if os.path.isfile(os.path.join(path, "task.toml")):
        return path
    containers = [path] if os.path.basename(path) in TASKS_DIR_NAMES else []
    containers += [os.path.join(path, n) for n in TASKS_DIR_NAMES]
    for c in containers:
        if os.path.isfile(os.path.join(c, "task.toml")):
            return c
        kids = _task_children(c)
        if len(kids) == 1:
            return os.path.join(c, kids[0])
        if kids:
            raise AmbiguousLayout(c, kids)
    return None


def deliverables_root(task_dir):
    """The folder holding Tasks/ and the run folders, for a task dir in either layout."""
    parent = os.path.dirname(os.path.abspath(task_dir))
    if os.path.basename(parent) in TASKS_DIR_NAMES:
        return os.path.dirname(parent)       # <root>/Tasks/<name>  -> <root>
    return parent                            # <root>/Tasks         -> <root>


def resolve_layout(path):
    """(deliverables_root, task_dir). task_dir is None when no task.toml can be found; the root
    is then the path itself, so run-only callers (qc_gate on a bare root) still work."""
    task = find_task_dir(path)
    if task:
        return deliverables_root(task), task
    path = os.path.abspath(path)
    if os.path.basename(path) in TASKS_DIR_NAMES:
        return os.path.dirname(path), None
    return path, None


def _is_trial_dir(d):
    return (os.path.isdir(os.path.join(d, "verifier"))
            or os.path.isfile(os.path.join(d, "trial.log")))


def _subdirs(d):
    try:
        return [os.path.join(d, n) for n in os.listdir(d) if os.path.isdir(os.path.join(d, n))]
    except OSError:
        return []


def run_path(root, run):
    """Where a run folder's job lives: <root>/<run>, except Trials. Reading Trials/ itself would mix
    the text-only attempts in without_images/ into the normal ones, so Trials resolves to
    Trials/with_images/. A Trials/ from before that split (no with_images/) is read as it is."""
    d = os.path.join(root, run)
    if run == "Trials" and os.path.isdir(os.path.join(d, "with_images")):
        return os.path.join(d, "with_images")
    return d


def find_trial_dirs(run_path):
    """Every trial dir under a run folder, newest first, whatever its name. Looks one level down
    (mm_run.sh's flat job) and two (a timestamped job dir inside the run folder)."""
    found = []
    for d in _subdirs(run_path):
        if _is_trial_dir(d):
            found.append(d)
        else:
            found += [t for t in _subdirs(d) if _is_trial_dir(t)]
    return sorted(found, key=lambda t: os.path.getmtime(t), reverse=True)


def trial_dir(run_path):
    """The newest trial dir under a run folder, or None."""
    t = find_trial_dirs(run_path)
    return t[0] if t else None


def job_dir(run_path):
    """The harbor job dir a run folder's newest trial belongs to - where config.json/result.json
    for the JOB live. Equals run_path for mm_run.sh's flat job."""
    t = trial_dir(run_path)
    return os.path.dirname(t) if t else run_path
