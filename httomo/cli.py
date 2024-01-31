from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePath
from shutil import copy
import tempfile
from typing import Optional, Union

import click
from mpi4py import MPI

import httomo.globals
from httomo.logger import setup_logger
from httomo.transform_layer import TransformLayer
from httomo.yaml_checker import validate_yaml_config
from httomo.runner.task_runner import TaskRunner
from httomo.ui_layer import UiLayer

from . import __version__


@click.group
@click.version_option(version=__version__, message="%(version)s")
def main():
    """httomo: Software for High Throughput Tomography in parallel beam.

    Use `python -m httomo run --help` for more help on the runner.
    """
    pass


@main.command()
@click.argument(
    "in_data_file", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.argument(
    "yaml_config", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.argument(
    "out_dir",
    type=click.Path(exists=True, file_okay=False, writable=True, path_type=Path),
)
@click.option(
    "--save-all",
    is_flag=True,
    help="Save intermediate datasets for all tasks in the pipeline.",
)
@click.option(
    "--gpu-id",
    type=click.INT,
    default=-1,
    help="The GPU ID of the device to use.",
)
@click.option(
    "--reslice-dir",
    type=click.Path(exists=True, file_okay=False, writable=True, path_type=Path),
    default=None,
    help="Directory for temporary files potentially needed for reslicing (defaults to output dir)",
)
@click.option(
    "--max-cpu-slices",
    type=click.INT,
    default=64,
    help="Maximum number of slices to use for a block for CPU-only sections (default: 64)"
)
def run(
    in_data_file: Path,
    yaml_config: Path,
    out_dir: Path,
    gpu_id: int,
    save_all: bool,
    reslice_dir: Union[Path, None],
    max_cpu_slices: int
):
    """Run a pipeline defined in YAML on input data."""

    # First we need to validate yaml configuration file if there are any errors
    # TODO: with new yaml syntax check yaml is not fully working.
    # Need to re-enable that:
    # _check_yaml(yaml_config, in_data_file)

    if max_cpu_slices < 1:
        raise ValueError("max-cpu-slices must be greater or equal to 1")
    httomo.globals.MAX_CPU_SLICES = max_cpu_slices

    # Define httomo.globals.run_out_dir in all MPI processes
    httomo.globals.run_out_dir = out_dir.joinpath(
        f"{datetime.now().strftime('%d-%m-%Y_%H_%M_%S')}_output"
    )
    comm = MPI.COMM_WORLD
    if comm.rank == 0:
        # Setup global logger object
        httomo.globals.logger = setup_logger(httomo.globals.run_out_dir)

        # Copy YAML pipeline file to output directory
        copy(yaml_config, httomo.globals.run_out_dir)

    # try to access the GPU with the ID given
    try:
        import cupy as cp

        gpu_count = cp.cuda.runtime.getDeviceCount()

        if gpu_id != -1:
            if gpu_id not in range(0, gpu_count):
                raise ValueError(
                    f"GPU Device not available for access. Use a GPU ID in the range: 0 to {gpu_count} (exclusive)"
                )

            cp.cuda.Device(gpu_id).use()

        httomo.globals.gpu_id = gpu_id

    except ImportError:
        pass  # silently pass and run if the CPU pipeline is given

    # instantiate UiLayer class for pipeline build
    init_UiLayer = UiLayer(yaml_config, in_data_file, comm=comm)
    pipeline = init_UiLayer.build_pipeline()

    # perform transformations on pipeline
    tr = TransformLayer(comm=comm, save_all=save_all)
    pipeline = tr.transform(pipeline)

    # Run the pipeline using Taskrunner, with temp dir or reslice dir
    ctx: AbstractContextManager = nullcontext(reslice_dir)
    if reslice_dir is None:
        ctx = tempfile.TemporaryDirectory()
    with ctx as tmp_dir:
        runner = TaskRunner(pipeline, Path(tmp_dir))
        return runner.execute()


def _check_yaml(yaml_config: Path, in_data: Path):
    """Check a YAML pipeline file for errors."""
    return validate_yaml_config(yaml_config, in_data)
