from pathlib import Path
from typing import Optional
from mpi4py import MPI

from httomo.darks_flats import DarksFlatsFileConfig
from httomo.loaders.standard_tomo_loader import AnglesConfig, StandardLoaderWrapper
from httomo.preview import PreviewConfig
from httomo.runner.loader import LoaderInterface
from httomo.runner.methods_repository_interface import MethodRepository


def make_loader(
    repo: MethodRepository,
    module_path: str,
    method_name: str,
    in_file: Path,
    data_path: str,
    image_key_path: Optional[str],
    angles: AnglesConfig,
    darks: DarksFlatsFileConfig,
    flats: DarksFlatsFileConfig,
    preview: PreviewConfig,
    comm: MPI.Comm,
) -> LoaderInterface:
    """Produces a loader interface. Only StandardTomoWrapper is supported right now,
    and this method has been added for backwards compatibility. Supporting other loaders
    is a topic that still needs to be explored."""

    if "standard_tomo" not in method_name:
        raise NotImplementedError(
            "Only the standard_tomo loader is currently supported"
        )

    return StandardLoaderWrapper(
        comm=comm,
        in_file=in_file,
        data_path=data_path,
        image_key_path=image_key_path,
        darks=darks,
        flats=flats,
        angles=angles,
        preview=preview,
    )
