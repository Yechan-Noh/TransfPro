"""Background worker threads for TransfPro.

This package contains QObject-based worker classes that run in QThread
instances for non-blocking SSH operations, file transfers, and data
queries.

Typical usage:
    from transfpro.workers import SSHConnectWorker, JobQueryWorker
    from PyQt5.QtCore import QThread

    # Create a worker
    worker = JobQueryWorker(slurm_manager)

    # Create a thread and move worker to it
    thread = QThread()
    worker.moveToThread(thread)

    # Connect signals
    worker.jobs_updated.connect(on_jobs_received)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)

    # Start the thread
    thread.start()
"""

from .base_worker import BaseWorker
from .ssh_connect_worker import SSHConnectWorker, SSHDisconnectWorker
from .job_query_worker import JobQueryWorker
from .job_submit_worker import JobSubmitWorker
from .transfer_worker import TransferWorker
from .log_tail_worker import LogTailWorker
from .cluster_info_worker import ClusterInfoWorker
from .remote_browser_worker import RemoteBrowserWorker

__all__ = [
    "BaseWorker",
    "SSHConnectWorker",
    "SSHDisconnectWorker",
    "JobQueryWorker",
    "JobSubmitWorker",
    "TransferWorker",
    "LogTailWorker",
    "ClusterInfoWorker",
    "RemoteBrowserWorker",
]
