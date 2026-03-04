"""SLURM sbatch script templates for common GROMACS workflows."""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ExampleTemplates:
    """SLURM sbatch script templates for common GROMACS workflows."""

    TEMPLATES: Dict[str, Dict] = {
        "energy_minimization": {
            "name": "Energy Minimization",
            "description": "Minimize system energy using steepest descent algorithm",
            "workflow_type": "em",
            "default_values": {
                "job_name": "em",
                "partition": "default",
                "nodes": "1",
                "ntasks": "1",
                "cpus_per_task": "8",
                "time": "01:00:00",
                "output_file": "em.log",
                "gromacs_module": "gromacs/2021.4",
                "em_mdp": "em.mdp",
                "input_tpr": "em.tpr",
                "output_trr": "em.trr",
                "output_gro": "em.gro",
                "output_edr": "em.edr"
            },
            "script_template": """#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks={ntasks}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --time={time}
#SBATCH --output={output_file}

# Load GROMACS module
module load {gromacs_module}

# Energy minimization
echo "Starting energy minimization..."
gmx mdrun -deffnm em -c {output_gro} -e {output_edr} -o {output_trr}

echo "Energy minimization complete"
"""
        },

        "nvt_equilibration": {
            "name": "NVT Equilibration",
            "description": "Equilibrate system at constant temperature and volume",
            "workflow_type": "nvt",
            "default_values": {
                "job_name": "nvt",
                "partition": "default",
                "nodes": "1",
                "ntasks": "1",
                "cpus_per_task": "8",
                "time": "04:00:00",
                "output_file": "nvt.log",
                "gromacs_module": "gromacs/2021.4",
                "input_gro": "em.gro",
                "input_top": "topol.top",
                "nvt_mdp": "nvt.mdp",
                "output_gro": "nvt.gro",
                "output_trr": "nvt.trr",
                "output_edr": "nvt.edr"
            },
            "script_template": """#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks={ntasks}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --time={time}
#SBATCH --output={output_file}

# Load GROMACS module
module load {gromacs_module}

# Create TPR file for NVT equilibration
echo "Preparing NVT equilibration..."
gmx grompp -f {nvt_mdp} -c {input_gro} -p {input_top} -o nvt.tpr -v

# NVT equilibration
echo "Starting NVT equilibration..."
gmx mdrun -deffnm nvt -c {output_gro} -e {output_edr} -o {output_trr} -v

echo "NVT equilibration complete"
"""
        },

        "npt_equilibration": {
            "name": "NPT Equilibration",
            "description": "Equilibrate system at constant temperature and pressure",
            "workflow_type": "npt",
            "default_values": {
                "job_name": "npt",
                "partition": "default",
                "nodes": "1",
                "ntasks": "1",
                "cpus_per_task": "8",
                "time": "04:00:00",
                "output_file": "npt.log",
                "gromacs_module": "gromacs/2021.4",
                "input_gro": "nvt.gro",
                "input_top": "topol.top",
                "npt_mdp": "npt.mdp",
                "output_gro": "npt.gro",
                "output_trr": "npt.trr",
                "output_edr": "npt.edr"
            },
            "script_template": """#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks={ntasks}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --time={time}
#SBATCH --output={output_file}

# Load GROMACS module
module load {gromacs_module}

# Create TPR file for NPT equilibration
echo "Preparing NPT equilibration..."
gmx grompp -f {npt_mdp} -c {input_gro} -p {input_top} -o npt.tpr -v

# NPT equilibration
echo "Starting NPT equilibration..."
gmx mdrun -deffnm npt -c {output_gro} -e {output_edr} -o {output_trr} -v

echo "NPT equilibration complete"
"""
        },

        "production_md": {
            "name": "Production MD",
            "description": "Production molecular dynamics simulation",
            "workflow_type": "md",
            "default_values": {
                "job_name": "prod",
                "partition": "default",
                "nodes": "1",
                "ntasks": "1",
                "cpus_per_task": "8",
                "time": "24:00:00",
                "output_file": "prod.log",
                "gromacs_module": "gromacs/2021.4",
                "input_gro": "npt.gro",
                "input_top": "topol.top",
                "prod_mdp": "prod.mdp",
                "output_trr": "prod.trr",
                "output_edr": "prod.edr",
                "output_gro": "prod.gro"
            },
            "script_template": """#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks={ntasks}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --time={time}
#SBATCH --output={output_file}

# Load GROMACS module
module load {gromacs_module}

# Create TPR file for production run
echo "Preparing production simulation..."
gmx grompp -f {prod_mdp} -c {input_gro} -p {input_top} -o prod.tpr -v

# Production run
echo "Starting production simulation..."
gmx mdrun -deffnm prod -c {output_gro} -e {output_edr} -o {output_trr} -v

echo "Production simulation complete"
"""
        },

        "continuation": {
            "name": "Continuation Run",
            "description": "Continue simulation from checkpoint file",
            "workflow_type": "continuation",
            "default_values": {
                "job_name": "cont",
                "partition": "default",
                "nodes": "1",
                "ntasks": "1",
                "cpus_per_task": "8",
                "time": "24:00:00",
                "output_file": "cont.log",
                "gromacs_module": "gromacs/2021.4",
                "checkpoint_file": "prod.cpt",
                "tpr_file": "prod.tpr",
                "output_trr": "prod_cont.trr",
                "output_edr": "prod_cont.edr",
                "output_gro": "prod_cont.gro"
            },
            "script_template": """#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks={ntasks}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --time={time}
#SBATCH --output={output_file}

# Load GROMACS module
module load {gromacs_module}

# Continue simulation from checkpoint
echo "Continuing simulation from checkpoint..."
gmx mdrun -cpi {checkpoint_file} -deffnm prod -c {output_gro} -e {output_edr} -o {output_trr} -v

echo "Continuation run complete"
"""
        },

        "gpu_production": {
            "name": "GPU Production Run",
            "description": "GPU-accelerated production molecular dynamics simulation",
            "workflow_type": "gpu_md",
            "default_values": {
                "job_name": "gpu_prod",
                "partition": "gpu",
                "nodes": "1",
                "ntasks": "1",
                "cpus_per_task": "8",
                "gpus_per_task": "1",
                "time": "24:00:00",
                "output_file": "gpu_prod.log",
                "gromacs_module": "gromacs-gpu/2021.4",
                "input_gro": "npt.gro",
                "input_top": "topol.top",
                "prod_mdp": "prod.mdp",
                "output_trr": "prod.trr",
                "output_edr": "prod.edr",
                "output_gro": "prod.gro"
            },
            "script_template": """#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks={ntasks}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --gpus-per-task={gpus_per_task}
#SBATCH --time={time}
#SBATCH --output={output_file}

# Load GROMACS GPU module
module load {gromacs_module}

# Create TPR file for production run
echo "Preparing GPU-accelerated production simulation..."
gmx grompp -f {prod_mdp} -c {input_gro} -p {input_top} -o prod.tpr -v

# Production run with GPU
echo "Starting GPU-accelerated production simulation..."
gmx mdrun -deffnm prod -c {output_gro} -e {output_edr} -o {output_trr} -nb gpu -v

echo "GPU production simulation complete"
"""
        },

        "mpi_production": {
            "name": "MPI Production Run",
            "description": "Multi-node MPI molecular dynamics simulation",
            "workflow_type": "mpi_md",
            "default_values": {
                "job_name": "mpi_prod",
                "partition": "default",
                "nodes": "4",
                "ntasks_per_node": "2",
                "cpus_per_task": "4",
                "time": "24:00:00",
                "output_file": "mpi_prod.log",
                "gromacs_module": "gromacs/2021.4",
                "input_gro": "npt.gro",
                "input_top": "topol.top",
                "prod_mdp": "prod.mdp",
                "output_trr": "prod.trr",
                "output_edr": "prod.edr",
                "output_gro": "prod.gro"
            },
            "script_template": """#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks-per-node={ntasks_per_node}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --time={time}
#SBATCH --output={output_file}

# Load GROMACS module
module load {gromacs_module}

# Create TPR file for production run
echo "Preparing MPI production simulation..."
gmx grompp -f {prod_mdp} -c {input_gro} -p {input_top} -o prod.tpr -v

# Production run with MPI
echo "Starting MPI production simulation on $SLURM_NTASKS processes..."
mpirun gmx mdrun -deffnm prod -c {output_gro} -e {output_edr} -o {output_trr} -v

echo "MPI production simulation complete"
"""
        }
    }

    @staticmethod
    def get_template(name: str) -> Optional[str]:
        """
        Get template script string.

        Args:
            name: Template name (key in TEMPLATES)

        Returns:
            Template script string, or None if not found
        """
        template_info = ExampleTemplates.TEMPLATES.get(name)
        if template_info:
            return template_info.get("script_template")
        return None

    @staticmethod
    def list_templates() -> List[Dict[str, str]]:
        """
        List all available templates with metadata.

        Returns:
            List of dictionaries with keys: name, description, workflow_type
        """
        templates_list = []
        for key, template_info in ExampleTemplates.TEMPLATES.items():
            templates_list.append({
                "id": key,
                "name": template_info.get("name", key),
                "description": template_info.get("description", ""),
                "workflow_type": template_info.get("workflow_type", "")
            })
        return templates_list

    @staticmethod
    def render_template(name: str, **kwargs) -> str:
        """
        Render template with provided values.

        Replaces placeholders with provided keyword arguments.

        Args:
            name: Template name
            **kwargs: Placeholder values

        Returns:
            Rendered script

        Raises:
            ValueError if template not found
        """
        template_info = ExampleTemplates.TEMPLATES.get(name)
        if not template_info:
            raise ValueError(f"Template '{name}' not found")

        template_script = template_info.get("script_template", "")

        # Get defaults and merge with provided kwargs
        defaults = template_info.get("default_values", {})
        all_values = {**defaults, **kwargs}

        # Replace placeholders
        rendered = template_script
        for key, value in all_values.items():
            placeholder = "{" + key + "}"
            rendered = rendered.replace(placeholder, str(value))

        logger.debug(f"Rendered template '{name}' with {len(all_values)} values")
        return rendered

    @staticmethod
    def get_default_values(name: str) -> Dict:
        """
        Get default placeholder values for a template.

        Args:
            name: Template name

        Returns:
            Dictionary of default values

        Raises:
            ValueError if template not found
        """
        template_info = ExampleTemplates.TEMPLATES.get(name)
        if not template_info:
            raise ValueError(f"Template '{name}' not found")

        return template_info.get("default_values", {}).copy()

    @staticmethod
    def validate_template(name: str) -> bool:
        """
        Validate that a template exists and is well-formed.

        Args:
            name: Template name

        Returns:
            True if valid
        """
        template_info = ExampleTemplates.TEMPLATES.get(name)
        if not template_info:
            return False

        required_keys = ["name", "description", "script_template"]
        for key in required_keys:
            if key not in template_info:
                logger.error(f"Template '{name}' missing required key: {key}")
                return False

        return True

    @staticmethod
    def get_templates_by_type(workflow_type: str) -> List[str]:
        """
        Get template names filtered by workflow type.

        Args:
            workflow_type: Workflow type to filter by

        Returns:
            List of template names
        """
        matching = []
        for name, info in ExampleTemplates.TEMPLATES.items():
            if info.get("workflow_type") == workflow_type:
                matching.append(name)
        return matching
