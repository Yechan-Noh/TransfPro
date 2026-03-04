"""Parse GROMACS log and mdp files for simulation progress.

This module is optional — GROMACS-specific features are only available
when this module can be imported.
"""

import logging
import re
from typing import Dict, Optional, List, Set
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# GROMACS file extension constants (moved from config/constants.py)
GROMACS_EXTENSIONS: Set[str] = {
    ".tpr", ".mdp", ".gro", ".top", ".xtc",
    ".edr", ".log", ".cpt", ".trr", ".xvg",
}

GROMACS_INPUT_EXTENSIONS: Set[str] = {".tpr", ".mdp", ".gro", ".top"}

GROMACS_OUTPUT_EXTENSIONS: Set[str] = {".xtc", ".edr", ".log", ".cpt", ".trr", ".xvg"}

# Pre-compiled regex patterns for performance optimization
_RE_STEP = re.compile(r'Step\s+(\d+),\s+Time\s+=\s+([\d.]+)\s+ps')
_RE_PERFORMANCE = re.compile(r'(\d+\.?\d*)\s+ns/day')
_RE_WALL_TIME = re.compile(r'Wall\s+time\s+since\s+start\s+([\d\sdhms]+)')
_RE_ETA = re.compile(r'ETA\s+=\s+([\d.]+)\s+ps')
_RE_FLOAT = re.compile(r'\d+\.\d+')
_RE_GROMACS_VERSION = re.compile(r'GROMACS version:\s+([\d.]+)')


class GromacsLogParser:
    """Parse GROMACS log and mdp files for simulation progress."""

    @staticmethod
    def parse_log_progress(log_content: str) -> Dict:
        """
        Extract simulation progress from GROMACS .log file.

        Args:
            log_content: Content of GROMACS .log file

        Returns:
            Dictionary with keys:
            - current_step: Current simulation step
            - current_time_ps: Current simulation time in picoseconds
            - ns_per_day: Performance (nanoseconds simulated per day)
            - wall_time: Wall clock time used
            - eta_ps: Estimated time to reach target (if available)
            - percent_complete: Completion percentage (0-100)
            - last_update: Timestamp of last update
        """
        progress = {
            'current_step': 0,
            'current_time_ps': 0.0,
            'ns_per_day': 0.0,
            'wall_time': '',
            'eta_ps': 0.0,
            'percent_complete': 0.0,
            'last_update': None
        }

        try:
            lines = log_content.split('\n')

            # Scan through lines to find latest values
            for line in reversed(lines):
                if not progress['current_step']:
                    step_match = _RE_STEP.search(line)
                    if step_match:
                        progress['current_step'] = int(step_match.group(1))
                        progress['current_time_ps'] = float(step_match.group(2))
                        progress['last_update'] = datetime.now()

                if not progress['ns_per_day']:
                    perf_match = _RE_PERFORMANCE.search(line)
                    if perf_match:
                        progress['ns_per_day'] = float(perf_match.group(1))

                if not progress['wall_time']:
                    time_match = _RE_WALL_TIME.search(line)
                    if time_match:
                        progress['wall_time'] = time_match.group(1).strip()

                if not progress['eta_ps']:
                    eta_match = _RE_ETA.search(line)
                    if eta_match:
                        progress['eta_ps'] = float(eta_match.group(1))

                # Break if we found everything
                if all([progress['current_step'], progress['ns_per_day'],
                       progress['wall_time'], progress['eta_ps']]):
                    break

            # Calculate percent complete if ETA is available
            if progress['eta_ps'] > 0 and progress['current_time_ps'] > 0:
                progress['percent_complete'] = min(
                    100.0,
                    (progress['current_time_ps'] / progress['eta_ps']) * 100
                )

            logger.debug(f"Parsed progress: {progress}")
            return progress

        except Exception as e:
            logger.error(f"Failed to parse log progress: {e}")
            return progress

    @staticmethod
    def parse_mdp_settings(mdp_content: str) -> Dict:
        """
        Extract simulation settings from GROMACS .mdp file.

        Args:
            mdp_content: Content of GROMACS .mdp file

        Returns:
            Dictionary with parsed settings including:
            - nsteps: Total number of simulation steps
            - dt: Time step in picoseconds
            - total_time_ps: Total simulation time
            - nstxout: Frequency of trajectory output
            - nstvout: Frequency of velocity output
            - nstenergy: Frequency of energy output
            - temperature: Target temperature (K)
            - pressure: Target pressure (bar)
            - pcouple: Pressure coupling algorithm
            - integrator: Integrator type
        """
        settings = {
            'nsteps': 0,
            'dt': 0.0,
            'total_time_ps': 0.0,
            'nstxout': 0,
            'nstvout': 0,
            'nstenergy': 0,
            'temperature': 0.0,
            'pressure': 0.0,
            'pcouple': '',
            'integrator': '',
            'all_settings': {}
        }

        try:
            # Parse key = value format
            for line in mdp_content.split('\n'):
                # Skip comments and empty lines
                if not line.strip() or line.strip().startswith(';'):
                    continue

                # Remove inline comments
                if ';' in line:
                    line = line.split(';')[0]

                if '=' not in line:
                    continue

                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                # Store in all_settings
                settings['all_settings'][key] = value

                # Parse specific settings
                try:
                    if key == 'nsteps':
                        settings['nsteps'] = int(value)
                    elif key == 'dt':
                        settings['dt'] = float(value)
                    elif key == 'nstxout':
                        settings['nstxout'] = int(value)
                    elif key == 'nstvout':
                        settings['nstvout'] = int(value)
                    elif key == 'nstenergy':
                        settings['nstenergy'] = int(value)
                    elif key == 'ref_t':
                        # May contain multiple values, take first
                        parts = value.split()
                        if parts:
                            settings['temperature'] = float(parts[0])
                    elif key == 'ref_p':
                        # May contain multiple values, take first
                        parts = value.split()
                        if parts:
                            settings['pressure'] = float(parts[0])
                    elif key == 'pcouple':
                        settings['pcouple'] = value
                    elif key == 'integrator':
                        settings['integrator'] = value
                except (ValueError, IndexError) as e:
                    logger.debug(f"Could not parse {key}={value}: {e}")

            # Calculate total simulation time
            if settings['nsteps'] > 0 and settings['dt'] > 0:
                settings['total_time_ps'] = settings['nsteps'] * settings['dt']

            logger.debug(f"Parsed MDP settings: nsteps={settings['nsteps']}, "
                        f"dt={settings['dt']}, total_time={settings['total_time_ps']}ps")
            return settings

        except Exception as e:
            logger.error(f"Failed to parse MDP settings: {e}")
            return settings

    @staticmethod
    def calculate_progress(current_step: int, total_steps: int) -> float:
        """
        Calculate completion percentage.

        Args:
            current_step: Current simulation step
            total_steps: Total simulation steps

        Returns:
            Completion percentage (0-100)
        """
        if total_steps <= 0:
            return 0.0

        return min(100.0, (current_step / total_steps) * 100)

    @staticmethod
    def estimate_completion(
        current_step: int,
        total_steps: int,
        ns_per_day: float,
        dt_ps: float
    ) -> Optional[datetime]:
        """
        Estimate simulation completion datetime.

        Args:
            current_step: Current simulation step
            total_steps: Total simulation steps
            ns_per_day: Current performance (ns/day)
            dt_ps: Time step in picoseconds

        Returns:
            Estimated completion datetime, or None if cannot estimate
        """
        try:
            if total_steps <= current_step or ns_per_day <= 0 or dt_ps <= 0:
                return None

            # Calculate remaining steps and time
            remaining_steps = total_steps - current_step
            remaining_time_ps = remaining_steps * dt_ps
            remaining_time_ns = remaining_time_ps / 1000

            # Calculate time to completion in days
            days_remaining = remaining_time_ns / ns_per_day

            # Estimate completion
            completion = datetime.now() + timedelta(days=days_remaining)

            logger.debug(f"Estimated completion in {days_remaining:.2f} days: {completion}")
            return completion

        except Exception as e:
            logger.error(f"Failed to estimate completion: {e}")
            return None

    @staticmethod
    def parse_energy_log(edr_output: str) -> Dict[str, List[float]]:
        """
        Parse output from 'gmx energy' command.

        Expects output format with columns of energy values.

        Args:
            edr_output: Output from gmx energy command

        Returns:
            Dictionary mapping energy type to list of values
        """
        energies = {}

        try:
            lines = edr_output.strip().split('\n')

            # Skip header lines (usually contain dashes or metadata)
            data_start = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('-') or not line.strip():
                    continue
                # Check if line contains numeric data
                if _RE_FLOAT.search(line):
                    data_start = i
                    break

            # Try to identify column headers
            headers = []
            for i in range(data_start - 1, -1, -1):
                line = lines[i].strip()
                if line and not line.startswith('-'):
                    # This might be the header line
                    potential_headers = line.split()
                    if len(potential_headers) > 2:  # Reasonable number of columns
                        headers = potential_headers
                        break

            if not headers:
                headers = [f"Col{i}" for i in range(10)]

            # Parse data lines
            for line in lines[data_start:]:
                line = line.strip()
                if not line or line.startswith('-'):
                    continue

                values = line.split()
                if len(values) > 0:
                    # First value is usually time/step
                    try:
                        time_val = float(values[0])
                        for j, val in enumerate(values[1:], 1):
                            if j < len(headers):
                                header = headers[j]
                                if header not in energies:
                                    energies[header] = []
                                try:
                                    energies[header].append(float(val))
                                except ValueError:
                                    pass
                    except ValueError:
                        pass

            logger.debug(f"Parsed energy data with {len(energies)} columns")
            return energies

        except Exception as e:
            logger.error(f"Failed to parse energy log: {e}")
            return energies

    @staticmethod
    def detect_simulation_type(mdp_content: str) -> str:
        """
        Detect simulation type from MDP file.

        Args:
            mdp_content: Content of MDP file

        Returns:
            Simulation type: "EM", "NVT", "NPT", "Production", etc.
        """
        try:
            mdp_lower = mdp_content.lower()

            if 'minimization' in mdp_lower or 'steep' in mdp_lower:
                return "Energy Minimization"
            elif 'nvt' in mdp_lower:
                return "NVT Equilibration"
            elif 'npt' in mdp_lower:
                return "NPT Equilibration"
            else:
                # Check integrator
                if 'integrator' in mdp_lower:
                    if 'md' in mdp_lower:
                        return "Production MD"
                    elif 'sd' in mdp_lower:
                        return "Steepest Descent"
                    elif 'cg' in mdp_lower:
                        return "Conjugate Gradient"

            return "Unknown"

        except Exception as e:
            logger.debug(f"Could not detect simulation type: {e}")
            return "Unknown"

    @staticmethod
    def extract_gromacs_version(log_content: str) -> Optional[str]:
        """
        Extract GROMACS version from log file.

        Args:
            log_content: Content of log file

        Returns:
            Version string (e.g., "2021.4"), or None if not found
        """
        try:
            match = _RE_GROMACS_VERSION.search(log_content)
            if match:
                version = match.group(1)
                logger.debug(f"Detected GROMACS version: {version}")
                return version
        except Exception as e:
            logger.debug(f"Could not extract GROMACS version: {e}")

        return None

    @staticmethod
    def extract_simulation_metadata(log_content: str) -> Dict:
        """
        Extract general simulation metadata from log file.

        Args:
            log_content: Content of log file

        Returns:
            Dictionary with metadata
        """
        metadata = {
            'version': None,
            'start_time': None,
            'title': '',
            'warnings': [],
            'errors': []
        }

        try:
            lines = log_content.split('\n')

            for line in lines:
                # Extract version
                if 'GROMACS version' in line and not metadata['version']:
                    match = _RE_GROMACS_VERSION.search(line)
                    if match:
                        metadata['version'] = match.group(1)

                # Extract title
                if 'Title string' in line or 'title' in line.lower():
                    parts = line.split(':', 1)
                    if len(parts) > 1:
                        metadata['title'] = parts[1].strip()

                # Extract warnings
                if 'WARNING' in line:
                    metadata['warnings'].append(line.strip())

                # Extract errors
                if 'ERROR' in line:
                    metadata['errors'].append(line.strip())

            logger.debug(f"Extracted metadata: version={metadata['version']}, "
                        f"warnings={len(metadata['warnings'])}, errors={len(metadata['errors'])}")
            return metadata

        except Exception as e:
            logger.error(f"Failed to extract metadata: {e}")
            return metadata
