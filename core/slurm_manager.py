"""Execute and parse SLURM commands."""

import logging
import json
import re
import shlex
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass, field
from datetime import datetime
from paramiko.ssh_exception import SSHException

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class JobInfo:
    """Job information from SLURM."""
    job_id: str
    name: str
    user: str
    state: str
    queue: str = ""
    nodes: int = 0
    cpus: int = 0
    memory_gb: float = 0.0
    time_limit: str = ""
    elapsed: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    node_list: str = ""
    exit_code: int = -1
    priority: float = 0.0
    submission_time: Optional[datetime] = None
    metadata: Dict = field(default_factory=dict)


@dataclass(slots=True)
class PartitionInfo:
    """Partition (queue) information."""
    name: str
    total_nodes: int = 0
    idle_nodes: int = 0
    allocated_nodes: int = 0
    other_nodes: int = 0
    cpus_per_node: int = 0
    memory_per_node_gb: float = 0.0
    default: bool = False
    state: str = "up"
    features: List[str] = field(default_factory=list)


@dataclass(slots=True)
class StorageInfo:
    """Storage/disk information."""
    path: str
    used_gb: float
    total_gb: float
    percent_used: float
    inode_used: int = 0
    inode_total: int = 0


class SLURMManager:
    """Execute and parse SLURM commands."""

    def __init__(self, ssh_manager):
        """
        Initialize SLURM manager.

        Args:
            ssh_manager: SSHManager instance
        """
        self.ssh = ssh_manager

    def get_jobs(self, user: Optional[str] = None) -> List[JobInfo]:
        """
        Get current jobs via squeue.

        Parses JSON output.

        Args:
            user: Optional username to filter jobs

        Returns:
            List of JobInfo objects

        Raises:
            SSHException if command fails
        """
        try:
            # Only fetch active jobs (exclude old CANCELLED/COMPLETED/FAILED)
            states = "PENDING,RUNNING,SUSPENDED,COMPLETING,CONFIGURING,RESIZING,REQUEUED"
            if user:
                command = f"squeue -u {shlex.quote(user)} --states={states} --json"
            else:
                command = f"squeue --states={states} --json"

            logger.info(f"Executing: {command}")
            stdout, stderr, exit_code = self.ssh.execute_command(command)

            if exit_code != 0:
                logger.error(f"squeue failed: {stderr}")
                return []

            return self._parse_squeue_json(stdout)

        except Exception as e:
            logger.error(f"Failed to get jobs: {e}")
            raise SSHException(f"Failed to get jobs: {e}")

    def get_job_history(self, user: Optional[str] = None, days: int = 30) -> List[JobInfo]:
        """
        Get historical jobs via sacct.

        Args:
            user: Optional username to filter jobs
            days: Number of days to look back

        Returns:
            List of JobInfo objects

        Raises:
            SSHException if command fails
        """
        try:
            if user:
                command = f"sacct -u {shlex.quote(user)} --json --starttime=now-{int(days)}days"
            else:
                command = f"sacct --json --starttime=now-{int(days)}days"

            logger.info(f"Executing: {command}")
            stdout, stderr, exit_code = self.ssh.execute_command(command)

            if exit_code != 0:
                logger.error(f"sacct failed: {stderr}")
                return []

            return self._parse_sacct_json(stdout)

        except Exception as e:
            logger.error(f"Failed to get job history: {e}")
            raise SSHException(f"Failed to get job history: {e}")

    def get_job_details(self, job_id: str) -> JobInfo:
        """
        Get detailed info for a single job via scontrol.

        Args:
            job_id: Job ID

        Returns:
            JobInfo object

        Raises:
            SSHException if command fails
        """
        try:
            command = f"scontrol show job {shlex.quote(str(job_id))}"
            logger.info(f"Executing: {command}")
            stdout, stderr, exit_code = self.ssh.execute_command(command)

            if exit_code != 0:
                raise SSHException(f"scontrol failed: {stderr}")

            # Parse scontrol output format
            job = JobInfo(
                job_id=job_id,
                name="",
                user="",
                state=""
            )

            # scontrol output has space-separated KEY=VALUE pairs on each line
            for line in stdout.split('\n'):
                # Split on spaces, then each token is KEY=VALUE
                for token in line.strip().split():
                    if '=' not in token:
                        continue
                    key, value = token.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    try:
                        if key == 'JobId':
                            job.job_id = value
                        elif key == 'JobName':
                            job.name = value
                        elif key == 'UserId':
                            job.user = value.split('(')[0]
                        elif key == 'JobState':
                            parts = value.split()
                            job.state = parts[0] if parts else value
                        elif key == 'Partition':
                            job.queue = value
                        elif key == 'NumNodes':
                            job.nodes = int(value)
                        elif key == 'NumCPUs':
                            job.cpus = int(value)
                        elif key == 'MinMemoryCPU':
                            if value.endswith('M'):
                                job.memory_gb = float(value[:-1]) / 1024
                            elif value.endswith('G'):
                                job.memory_gb = float(value[:-1])
                        elif key == 'TimeLimit':
                            job.time_limit = value
                        elif key == 'RunTime':
                            job.elapsed = value
                        elif key == 'NodeList':
                            job.node_list = value
                    except (ValueError, IndexError) as e:
                        logger.debug(f"Failed to parse scontrol field {key}={value}: {e}")

            logger.debug(f"Retrieved details for job {job_id}")
            return job

        except Exception as e:
            logger.error(f"Failed to get job details: {e}")
            raise SSHException(f"Failed to get job details: {e}")

    def submit_job(self, script_content: str, remote_dir: str) -> str:
        """
        Upload sbatch script and submit.

        Args:
            script_content: SLURM sbatch script content
            remote_dir: Remote directory to upload script to

        Returns:
            Job ID

        Raises:
            SSHException if submission fails
        """
        try:
            # Create script on remote
            remote_script = f"{remote_dir}/submit.sh"

            # Write script via SSH
            cat_command = f"cat > {shlex.quote(remote_script)} << 'EOF'\n{script_content}\nEOF"
            logger.info(f"Writing script to {remote_script}")
            stdout, stderr, exit_code = self.ssh.execute_command(cat_command)

            if exit_code != 0:
                raise SSHException(f"Failed to write script: {stderr}")

            # Submit job
            submit_command = f"sbatch {shlex.quote(remote_script)}"
            logger.info(f"Submitting job with: {submit_command}")
            stdout, stderr, exit_code = self.ssh.execute_command(submit_command)

            if exit_code != 0:
                raise SSHException(f"sbatch failed: {stderr}")

            # Parse job ID from output
            # Expected format: "Submitted batch job 123456"
            match = re.search(r'Submitted batch job (\d+)', stdout)
            if not match:
                raise SSHException(f"Could not parse job ID from: {stdout}")

            job_id = match.group(1)
            logger.info(f"Job submitted successfully: {job_id}")
            return job_id

        except Exception as e:
            logger.error(f"Failed to submit job: {e}")
            raise SSHException(f"Failed to submit job: {e}")

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel job with scancel.

        Args:
            job_id: Job ID to cancel

        Returns:
            True if successful

        Raises:
            SSHException if command fails
        """
        try:
            command = f"scancel {shlex.quote(str(job_id))}"
            logger.info(f"Executing: {command}")
            stdout, stderr, exit_code = self.ssh.execute_command(command)

            if exit_code != 0:
                logger.error(f"scancel failed: {stderr}")
                return False

            logger.info(f"Job {job_id} cancelled")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel job: {e}")
            raise SSHException(f"Failed to cancel job: {e}")

    def get_partitions(self) -> List[PartitionInfo]:
        """
        Get cluster partition info via sinfo.

        Args:
            None

        Returns:
            List of PartitionInfo objects

        Raises:
            SSHException if command fails
        """
        try:
            command = "sinfo --json"
            logger.info("Executing: sinfo --json")
            stdout, stderr, exit_code = self.ssh.execute_command(command)

            if exit_code != 0:
                logger.error(f"sinfo failed: {stderr}")
                return []

            return self._parse_sinfo_json(stdout)

        except Exception as e:
            logger.error(f"Failed to get partitions: {e}")
            raise SSHException(f"Failed to get partitions: {e}")

    def get_cluster_usage(self) -> Tuple[int, int, int, int]:
        """
        Get cluster resource usage.

        Args:
            None

        Returns:
            Tuple of (cpus_used, cpus_total, mem_used_gb, mem_total_gb)

        Raises:
            SSHException if command fails
        """
        try:
            command = "sinfo --Node --json"
            logger.info("Executing: sinfo --Node --json")
            stdout, stderr, exit_code = self.ssh.execute_command(command)

            if exit_code != 0:
                raise SSHException(f"sinfo failed: {stderr}")

            data = json.loads(stdout)
            nodes = data.get('nodes', [])

            cpus_used = 0
            cpus_total = 0
            mem_used_gb = 0
            mem_total_gb = 0

            for node in nodes:
                # Parse CPU info (handle nested dicts in newer SLURM)
                cpus_alloc = self._extract_number(node.get('alloc_cpus', node.get('cpus_alloc', 0)))
                cpus_node = self._extract_number(node.get('cpus', 0))
                cpus_used += cpus_alloc
                cpus_total += cpus_node

                # Parse memory info (handle nested dicts)
                mem_alloc = self._extract_number(node.get('alloc_memory', node.get('mem_alloc_mb', 0)))
                mem_node = self._extract_number(node.get('real_memory', node.get('mem_mb', 0)))
                mem_used_gb += mem_alloc / 1024
                mem_total_gb += mem_node / 1024

            logger.debug(f"Cluster usage: {cpus_used}/{cpus_total} CPUs, "
                        f"{mem_used_gb:.1f}/{mem_total_gb:.1f} GB RAM")
            return cpus_used, cpus_total, int(mem_used_gb), int(mem_total_gb)

        except Exception as e:
            logger.error(f"Failed to get cluster usage: {e}")
            raise SSHException(f"Failed to get cluster usage: {e}")

    def get_disk_usage(self, paths: Optional[List[str]] = None) -> List[StorageInfo]:
        """
        Get disk usage for given paths.

        Args:
            paths: List of paths to check. If None, uses common defaults.

        Returns:
            List of StorageInfo objects

        Raises:
            SSHException if command fails
        """
        try:
            if not paths:
                # Common default paths
                paths = ["/home", "/scratch", "/data"]

            storage_info = []

            for path in paths:
                try:
                    # Single SSH command: check exists + get used + get total
                    qpath = shlex.quote(path)
                    combined_cmd = (
                        f"if [ -d {qpath} ]; then "
                        f"echo EXISTS; "
                        f"du -s --block-size=1G {qpath} 2>/dev/null | awk '{{print $1}}'; "
                        f"df --block-size=1G {qpath} 2>/dev/null | tail -1 | awk '{{print $2}}'; "
                        f"else echo NOTFOUND; fi"
                    )
                    stdout, _, code = self.ssh.execute_command(combined_cmd, timeout=60)
                    lines = stdout.strip().split('\n')

                    if not lines or lines[0].strip() != 'EXISTS':
                        logger.debug(f"Path not found: {path}")
                        continue

                    used_gb = float(lines[1].strip()) if len(lines) > 1 and lines[1].strip() else 0
                    total_gb = float(lines[2].strip()) if len(lines) > 2 and lines[2].strip() else 0
                    percent_used = (used_gb / total_gb * 100) if total_gb > 0 else 0

                    storage_info.append(StorageInfo(
                        path=path,
                        used_gb=used_gb,
                        total_gb=total_gb,
                        percent_used=percent_used
                    ))

                    logger.debug(f"Storage {path}: {used_gb:.1f}GB / {total_gb:.1f}GB")

                except Exception as e:
                    logger.warning(f"Failed to get usage for {path}: {e}")

            return storage_info

        except Exception as e:
            logger.error(f"Failed to get disk usage: {e}")
            raise SSHException(f"Failed to get disk usage: {e}")

    def get_available_modules(self, pattern: str = "gromacs") -> List[str]:
        """
        Get available module versions matching pattern.

        Args:
            pattern: Module name pattern to search for

        Returns:
            List of available module names

        Raises:
            SSHException if command fails
        """
        try:
            # Use 'module avail' with grep
            command = f"module avail {pattern} 2>&1"
            logger.info(f"Executing: {command}")
            stdout, stderr, exit_code = self.ssh.execute_command(command)

            modules = []

            for line in stdout.split('\n'):
                line = line.strip()
                if line and not line.startswith('-') and '/' in line:
                    # Extract module name (format: "module/version")
                    modules.append(line)

            logger.debug(f"Found {len(modules)} modules matching '{pattern}'")
            return modules

        except Exception as e:
            logger.error(f"Failed to get modules: {e}")
            raise SSHException(f"Failed to get modules: {e}")

    @staticmethod
    def _extract_number(value, default=0):
        """
        Extract a numeric value from SLURM JSON fields.

        Newer SLURM versions (21.08+) wrap numeric values in objects like:
            {"number": 12345, "set": true, "infinite": false}
        This helper handles both old (plain int/float) and new (dict) formats.

        Args:
            value: Raw value from JSON (int, float, dict, or None)
            default: Default value if extraction fails

        Returns:
            Extracted numeric value
        """
        if value is None:
            return default
        if isinstance(value, dict):
            if value.get('infinite', False):
                return default
            return value.get('number', default)
        if isinstance(value, (int, float)):
            return value
        return default

    @staticmethod
    def _extract_string(value, default=''):
        """
        Extract a string value from SLURM JSON fields.

        Handles list-of-strings (e.g. job_state: ["RUNNING"]) and plain strings.

        Args:
            value: Raw value from JSON (str, list, or None)
            default: Default value if extraction fails

        Returns:
            Extracted string value
        """
        if value is None:
            return default
        if isinstance(value, list):
            return value[0] if value else default
        if isinstance(value, str):
            return value
        return str(value)

    @staticmethod
    def _extract_timestamp(value):
        """
        Extract a datetime from SLURM JSON timestamp fields.

        Handles both plain epoch ints and {"number": epoch, "set": true} dicts.
        Returns None for unset or zero timestamps.

        Args:
            value: Raw timestamp value from JSON

        Returns:
            datetime or None
        """
        if value is None:
            return None
        epoch = value
        if isinstance(value, dict):
            if not value.get('set', True):
                return None
            epoch = value.get('number', 0)
        if isinstance(epoch, (int, float)) and epoch > 0:
            try:
                return datetime.fromtimestamp(epoch)
            except (OSError, ValueError, OverflowError):
                return None
        return None

    @staticmethod
    def _format_seconds(seconds_val):
        """
        Format seconds (int or dict) into HH:MM:SS or SLURM time string.

        Args:
            seconds_val: Seconds value (int, dict with 'number', or str)

        Returns:
            Formatted time string
        """
        if isinstance(seconds_val, str):
            return seconds_val
        if isinstance(seconds_val, dict):
            if seconds_val.get('infinite', False):
                return "UNLIMITED"
            seconds_val = seconds_val.get('number', 0)
        if not isinstance(seconds_val, (int, float)):
            return ""
        total = int(seconds_val)
        if total <= 0:
            return "0:00:00"
        days, remainder = divmod(total, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, secs = divmod(remainder, 60)
        if days > 0:
            return f"{days}-{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{hours}:{minutes:02d}:{secs:02d}"

    def _parse_squeue_json(self, json_str: str) -> List[JobInfo]:
        """
        Parse squeue JSON output to JobInfo list.

        Handles both older SLURM JSON formats (plain values) and newer
        SLURM 21.08+ formats (nested dict objects with 'number'/'set'/'infinite').

        Args:
            json_str: JSON string from squeue

        Returns:
            List of JobInfo objects
        """
        try:
            data = json.loads(json_str)
            jobs = []

            for job_data in data.get('jobs', []):
                try:
                    # Parse timestamps (handle both plain epoch and dict format)
                    start_time = self._extract_timestamp(job_data.get('start_time'))

                    # Parse job_state: can be "RUNNING" or ["RUNNING"]
                    state = self._extract_string(job_data.get('job_state', ''))

                    # Parse numeric fields (handle both plain int and dict format)
                    num_nodes = self._extract_number(job_data.get('node_count',
                                    job_data.get('num_nodes', 0)))
                    num_cpus = self._extract_number(job_data.get('cpus',
                                    job_data.get('num_cpus', 0)))

                    # Memory: may be dict or nested under 'memory_per_node'
                    mem_raw = job_data.get('memory_per_node', 0)
                    mem_val = self._extract_number(mem_raw, 0)
                    memory_gb = mem_val / 1024 if mem_val else 0

                    # Time limit (SLURM JSON gives this in MINUTES)
                    time_limit_raw = job_data.get('time_limit',
                                        job_data.get('time_limit', ''))
                    time_limit_min = self._extract_number(time_limit_raw, 0)
                    time_limit = self._format_seconds(time_limit_min * 60) if time_limit_min > 0 else self._format_seconds(time_limit_raw)

                    # Node list: may be a string or empty
                    node_list = job_data.get('nodes', '')
                    if isinstance(node_list, (list, dict)):
                        node_list = str(node_list)

                    # Exit code
                    exit_raw = job_data.get('exit_code', -1)
                    if isinstance(exit_raw, dict):
                        # Format: {"status": ["SUCCESS"], "return_code": {"number": 0}}
                        rc = exit_raw.get('return_code', exit_raw)
                        exit_code = self._extract_number(rc, -1)
                    else:
                        exit_code = self._extract_number(exit_raw, -1)

                    # Priority
                    priority = float(self._extract_number(job_data.get('priority', 0.0), 0.0))

                    # User name
                    user = job_data.get('user_name', job_data.get('user', ''))

                    # Elapsed: try JSON field first, fall back to start_time diff
                    elapsed_raw = job_data.get('time', {}).get('elapsed',
                                    job_data.get('elapsed', ''))
                    elapsed_secs = self._extract_number(elapsed_raw, 0)
                    if elapsed_secs <= 0 and start_time and state == 'RUNNING':
                        elapsed_secs = int((datetime.now() - start_time).total_seconds())
                    elapsed_str = self._format_seconds(elapsed_secs) if elapsed_secs > 0 else ''

                    # Submission time
                    submit_time = self._extract_timestamp(
                        job_data.get('time', {}).get('submission',
                            job_data.get('submit_time', None)))

                    job = JobInfo(
                        job_id=str(self._extract_number(job_data.get('job_id', ''), '')),
                        name=job_data.get('name', ''),
                        user=user,
                        state=state,
                        queue=job_data.get('partition', ''),
                        nodes=int(num_nodes),
                        cpus=int(num_cpus),
                        memory_gb=memory_gb,
                        time_limit=time_limit,
                        elapsed=elapsed_str,
                        start_time=start_time,
                        node_list=node_list,
                        exit_code=int(exit_code),
                        priority=priority,
                        submission_time=submit_time,
                        metadata=job_data
                    )
                    jobs.append(job)

                except Exception as e:
                    logger.warning(f"Failed to parse job: {e}", exc_info=True)

            logger.debug(f"Parsed {len(jobs)} jobs from squeue output")
            return jobs

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse squeue JSON: {e}")
            return []

    def _parse_sacct_json(self, json_str: str) -> List[JobInfo]:
        """
        Parse sacct JSON output to JobInfo list.

        Handles both older and newer SLURM JSON formats.

        Args:
            json_str: JSON string from sacct

        Returns:
            List of JobInfo objects
        """
        try:
            data = json.loads(json_str)
            jobs = []

            for job_data in data.get('jobs', []):
                try:
                    # Parse timestamps (handle dict and plain epoch)
                    start_time = self._extract_timestamp(
                        job_data.get('time', {}).get('start', job_data.get('start')))
                    end_time = self._extract_timestamp(
                        job_data.get('time', {}).get('end', job_data.get('end')))
                    submit_time = self._extract_timestamp(
                        job_data.get('time', {}).get('submission', job_data.get('submit')))

                    state_raw = job_data.get('state', job_data.get('job_state', ''))
                    state = self._extract_string(state_raw)
                    # sacct state can include info like "COMPLETED by 0"
                    if isinstance(state_raw, dict):
                        state = state_raw.get('current', state_raw.get('previous', ['UNKNOWN']))
                        state = self._extract_string(state)

                    nodes_raw = job_data.get('allocation_nodes', job_data.get('nodes', 0))
                    nodes_val = self._extract_number(nodes_raw, 0)
                    # 'nodes' may be a string nodelist for sacct, handle it
                    node_list = ''
                    if isinstance(nodes_raw, str) and not nodes_raw.isdigit():
                        node_list = nodes_raw
                        nodes_val = 0

                    cpus_val = self._extract_number(
                        job_data.get('required', {}).get('CPUs', job_data.get('cpus', 0)), 0)

                    mem_raw = job_data.get('required', {}).get('memory_per_node',
                                job_data.get('memory', 0))
                    mem_val = self._extract_number(mem_raw, 0)
                    memory_gb = mem_val / 1024 if mem_val else 0

                    # Time limit (SLURM JSON gives this in MINUTES)
                    time_limit_raw = job_data.get('time', {}).get('limit',
                                        job_data.get('timelimit', ''))
                    time_limit_min = self._extract_number(time_limit_raw, 0)
                    time_limit = self._format_seconds(time_limit_min * 60) if time_limit_min > 0 else self._format_seconds(time_limit_raw)

                    elapsed_raw = job_data.get('time', {}).get('elapsed',
                                    job_data.get('elapsed', ''))
                    elapsed = self._format_seconds(elapsed_raw)

                    exit_raw = job_data.get('exit_code', -1)
                    if isinstance(exit_raw, dict):
                        rc = exit_raw.get('return_code', exit_raw)
                        exit_code = self._extract_number(rc, -1)
                    else:
                        exit_code = self._extract_number(exit_raw, -1)

                    job = JobInfo(
                        job_id=str(self._extract_number(job_data.get('job_id', ''), '')),
                        name=job_data.get('name', ''),
                        user=job_data.get('user', ''),
                        state=state,
                        queue=job_data.get('partition', ''),
                        nodes=int(nodes_val),
                        cpus=int(cpus_val),
                        memory_gb=memory_gb,
                        time_limit=time_limit,
                        elapsed=elapsed,
                        start_time=start_time,
                        end_time=end_time,
                        node_list=node_list,
                        exit_code=int(exit_code),
                        submission_time=submit_time,
                        metadata=job_data
                    )
                    jobs.append(job)

                except Exception as e:
                    logger.warning(f"Failed to parse sacct job: {e}", exc_info=True)

            logger.debug(f"Parsed {len(jobs)} jobs from sacct output")
            return jobs

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse sacct JSON: {e}")
            return []

    def _parse_sinfo_json(self, json_str: str) -> List[PartitionInfo]:
        """
        Parse sinfo JSON output to PartitionInfo list.

        Args:
            json_str: JSON string from sinfo

        Returns:
            List of PartitionInfo objects
        """
        try:
            data = json.loads(json_str)
            partitions = []

            # sinfo --json may return 'sinfo' key or 'partitions' key
            part_list = data.get('partitions', data.get('sinfo', []))
            for part_data in part_list:
                try:
                    # Extract node counts (handle nested dict format)
                    node_data = part_data.get('node_count', {})
                    if isinstance(node_data, dict):
                        total_nodes = self._extract_number(node_data.get('total', 0))
                        idle_nodes = self._extract_number(node_data.get('idle', 0))
                        alloc_nodes = self._extract_number(node_data.get('allocated', 0))
                        other_nodes = self._extract_number(node_data.get('other', 0))
                    else:
                        total_nodes = self._extract_number(part_data.get('total_nodes', 0))
                        idle_nodes = self._extract_number(part_data.get('idle_nodes', 0))
                        alloc_nodes = self._extract_number(part_data.get('allocated_nodes', 0))
                        other_nodes = self._extract_number(part_data.get('other_nodes', 0))

                    partition = PartitionInfo(
                        name=part_data.get('name', part_data.get('partition', {}).get('name', '')),
                        total_nodes=int(total_nodes),
                        idle_nodes=int(idle_nodes),
                        allocated_nodes=int(alloc_nodes),
                        other_nodes=int(other_nodes),
                        default=part_data.get('default', False),
                        state=self._extract_string(part_data.get('state', 'up'))
                    )
                    partitions.append(partition)

                except Exception as e:
                    logger.warning(f"Failed to parse partition: {e}")

            logger.debug(f"Parsed {len(partitions)} partitions from sinfo output")
            return partitions

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse sinfo JSON: {e}")
            return []
