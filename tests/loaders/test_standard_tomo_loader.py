from pathlib import Path
from typing import Tuple
from unittest import mock

import h5py
import pytest
import numpy as np
from mpi4py import MPI
from pytest_mock import MockerFixture

from httomo.darks_flats import DarksFlatsFileConfig
from httomo.loaders.standard_tomo_loader import StandardTomoLoader
from httomo.loaders.types import RawAngles, UserDefinedAngles
from httomo.preview import PreviewConfig, PreviewDimConfig


def make_standard_tomo_loader() -> StandardTomoLoader:
    """
    Create an instance of `StandardTomoLoader` with some commonly used default values for
    loading the test data `tomo_standard.nxs`.
    """
    IN_FILE_PATH = Path(__file__).parent.parent / "test_data/tomo_standard.nxs"
    DARKS_FLATS_CONFIG = DarksFlatsFileConfig(
        file=IN_FILE_PATH,
        data_path="/entry1/tomo_entry/data/data",
        image_key_path="/entry1/tomo_entry/instrument/detector/image_key",
    )
    ANGLES_CONFIG = RawAngles(data_path="/entry1/tomo_entry/data/rotation_angle")
    PREVIEW_CONFIG = PreviewConfig(
        angles=PreviewDimConfig(start=0, stop=180),
        detector_y=PreviewDimConfig(start=0, stop=128),
        detector_x=PreviewDimConfig(start=0, stop=160),
    )
    SLICING_DIM = 0
    COMM = MPI.COMM_WORLD
    loader = StandardTomoLoader(
        in_file=IN_FILE_PATH,
        data_path=DARKS_FLATS_CONFIG.data_path,
        image_key_path=DARKS_FLATS_CONFIG.image_key_path,
        darks=DARKS_FLATS_CONFIG,
        flats=DARKS_FLATS_CONFIG,
        angles=ANGLES_CONFIG,
        preview_config=PREVIEW_CONFIG,
        slicing_dim=SLICING_DIM,
        comm=COMM,
    )
    return loader


def test_standard_tomo_loader_gives_h5py_dataset():
    with mock.patch(
        "httomo.darks_flats.get_darks_flats",
        return_value=(np.zeros(1), np.zeros(1)),
    ):
        loader = make_standard_tomo_loader()

    assert isinstance(loader._data, h5py.Dataset)


def test_standard_tomo_loader_get_slicing_dim():
    with mock.patch(
        "httomo.darks_flats.get_darks_flats",
        return_value=(np.zeros(1), np.zeros(1)),
    ):
        loader = make_standard_tomo_loader()
    assert loader.slicing_dim == 0


def test_standard_tomo_loader_get_chunk_index_single_proc():
    with mock.patch(
        "httomo.darks_flats.get_darks_flats",
        return_value=(np.zeros(1), np.zeros(1)),
    ):
        loader = make_standard_tomo_loader()
    CHUNK_INDEX = (0, 0, 0)
    assert loader.global_index == CHUNK_INDEX


@pytest.mark.mpi
@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2, reason="Only rank-2 MPI is supported with this test"
)
@pytest.mark.parametrize(
    "preview_config",
    [
        PreviewConfig(
            angles=PreviewDimConfig(start=0, stop=180),
            detector_y=PreviewDimConfig(start=0, stop=128),
            detector_x=PreviewDimConfig(start=0, stop=160),
        ),
        PreviewConfig(
            angles=PreviewDimConfig(start=0, stop=180),
            detector_y=PreviewDimConfig(start=5, stop=128),
            detector_x=PreviewDimConfig(start=0, stop=160),
        ),
        PreviewConfig(
            angles=PreviewDimConfig(start=0, stop=180),
            detector_y=PreviewDimConfig(start=0, stop=128),
            detector_x=PreviewDimConfig(start=5, stop=160),
        ),
    ],
    ids=["no_cropping", "crop_det_y", "crop_det_x"],
)
def test_standard_tomo_loader_previewed_get_chunk_index_two_procs(
    standard_data_path: str,
    standard_image_key_path: str,
    preview_config: PreviewConfig,
):
    DATA_SHAPE = (180, 128, 160)
    IN_FILE_PATH = Path(__file__).parent.parent / "test_data/tomo_standard.nxs"
    DARKS_FLATS_CONFIG = DarksFlatsFileConfig(
        file=IN_FILE_PATH,
        data_path=standard_data_path,
        image_key_path=standard_image_key_path,
    )
    ANGLES_CONFIG = RawAngles(data_path="/entry1/tomo_entry/data/rotation_angle")
    SLICING_DIM = 0
    COMM = MPI.COMM_WORLD

    chunk_index = (0, 0, 0) if COMM.rank == 0 else (DATA_SHAPE[0] // 2, 0, 0)

    with mock.patch(
        "httomo.darks_flats.get_darks_flats",
        return_value=(np.zeros(1), np.zeros(1)),
    ):
        loader = StandardTomoLoader(
            in_file=IN_FILE_PATH,
            data_path=DARKS_FLATS_CONFIG.data_path,
            image_key_path=DARKS_FLATS_CONFIG.image_key_path,
            darks=DARKS_FLATS_CONFIG,
            flats=DARKS_FLATS_CONFIG,
            angles=ANGLES_CONFIG,
            preview_config=preview_config,
            slicing_dim=SLICING_DIM,
            comm=COMM,
        )

    assert loader.global_index == chunk_index


@pytest.mark.parametrize(
    "preview_config, expected_chunk_shape",
    [
        (
            PreviewConfig(
                angles=PreviewDimConfig(start=0, stop=180),
                detector_y=PreviewDimConfig(start=0, stop=128),
                detector_x=PreviewDimConfig(start=0, stop=160),
            ),
            (180, 128, 160),
        ),
        (
            PreviewConfig(
                angles=PreviewDimConfig(start=0, stop=180),
                detector_y=PreviewDimConfig(start=5, stop=15),
                detector_x=PreviewDimConfig(start=0, stop=160),
            ),
            (180, 10, 160),
        ),
        (
            PreviewConfig(
                angles=PreviewDimConfig(start=0, stop=180),
                detector_y=PreviewDimConfig(start=0, stop=128),
                detector_x=PreviewDimConfig(start=5, stop=15),
            ),
            (180, 128, 10),
        ),
    ],
    ids=["no_cropping", "crop_det_y", "crop_det_x"],
)
def test_standard_tomo_loader_get_chunk_shape_single_proc(
    standard_data_path: str,
    standard_image_key_path: str,
    preview_config: PreviewConfig,
    expected_chunk_shape: Tuple[int, int, int],
):
    IN_FILE_PATH = Path(__file__).parent.parent / "test_data/tomo_standard.nxs"
    DARKS_FLATS_CONFIG = DarksFlatsFileConfig(
        file=IN_FILE_PATH,
        data_path=standard_data_path,
        image_key_path=standard_image_key_path,
    )
    ANGLES_CONFIG = RawAngles(data_path="/entry1/tomo_entry/data/rotation_angle")
    SLICING_DIM = 0
    COMM = MPI.COMM_WORLD

    with mock.patch(
        "httomo.darks_flats.get_darks_flats",
        return_value=(np.zeros(1), np.zeros(1)),
    ):
        loader = StandardTomoLoader(
            in_file=IN_FILE_PATH,
            data_path=DARKS_FLATS_CONFIG.data_path,
            image_key_path=DARKS_FLATS_CONFIG.image_key_path,
            darks=DARKS_FLATS_CONFIG,
            flats=DARKS_FLATS_CONFIG,
            angles=ANGLES_CONFIG,
            preview_config=preview_config,
            slicing_dim=SLICING_DIM,
            comm=COMM,
        )

    assert loader.chunk_shape == expected_chunk_shape


@pytest.mark.mpi
@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2, reason="Only rank-2 MPI is supported with this test"
)
@pytest.mark.parametrize(
    "preview_config, expected_chunk_shape",
    [
        (
            PreviewConfig(
                angles=PreviewDimConfig(start=0, stop=180),
                detector_y=PreviewDimConfig(start=0, stop=128),
                detector_x=PreviewDimConfig(start=0, stop=160),
            ),
            (90, 128, 160),
        ),
        (
            PreviewConfig(
                angles=PreviewDimConfig(start=0, stop=180),
                detector_y=PreviewDimConfig(start=5, stop=15),
                detector_x=PreviewDimConfig(start=0, stop=160),
            ),
            (90, 10, 160),
        ),
        (
            PreviewConfig(
                angles=PreviewDimConfig(start=0, stop=180),
                detector_y=PreviewDimConfig(start=0, stop=128),
                detector_x=PreviewDimConfig(start=5, stop=15),
            ),
            (90, 128, 10),
        ),
    ],
    ids=["no_cropping", "crop_det_y", "crop_det_x"],
)
def test_standard_tomo_loader_get_chunk_shape_two_procs(
    standard_data_path: str,
    standard_image_key_path: str,
    preview_config: PreviewConfig,
    expected_chunk_shape: Tuple[int, int, int],
):
    IN_FILE_PATH = Path(__file__).parent.parent / "test_data/tomo_standard.nxs"
    DARKS_FLATS_CONFIG = DarksFlatsFileConfig(
        file=IN_FILE_PATH,
        data_path=standard_data_path,
        image_key_path=standard_image_key_path,
    )
    ANGLES_CONFIG = RawAngles(data_path="/entry1/tomo_entry/data/rotation_angle")
    SLICING_DIM = 0
    COMM = MPI.COMM_WORLD

    with mock.patch(
        "httomo.darks_flats.get_darks_flats",
        return_value=(np.zeros(1), np.zeros(1)),
    ):
        loader = StandardTomoLoader(
            in_file=IN_FILE_PATH,
            data_path=DARKS_FLATS_CONFIG.data_path,
            image_key_path=DARKS_FLATS_CONFIG.image_key_path,
            darks=DARKS_FLATS_CONFIG,
            flats=DARKS_FLATS_CONFIG,
            angles=ANGLES_CONFIG,
            preview_config=preview_config,
            slicing_dim=SLICING_DIM,
            comm=COMM,
        )

    assert loader.chunk_shape == expected_chunk_shape


@pytest.mark.parametrize(
    "preview_config",
    [
        PreviewConfig(
            angles=PreviewDimConfig(start=0, stop=180),
            detector_y=PreviewDimConfig(start=0, stop=128),
            detector_x=PreviewDimConfig(start=0, stop=160),
        ),
        PreviewConfig(
            angles=PreviewDimConfig(start=0, stop=180),
            detector_y=PreviewDimConfig(start=0, stop=10),
            detector_x=PreviewDimConfig(start=0, stop=160),
        ),
        PreviewConfig(
            angles=PreviewDimConfig(start=0, stop=180),
            detector_y=PreviewDimConfig(start=10, stop=20),
            detector_x=PreviewDimConfig(start=0, stop=160),
        ),
        PreviewConfig(
            angles=PreviewDimConfig(start=0, stop=180),
            detector_y=PreviewDimConfig(start=0, stop=128),
            detector_x=PreviewDimConfig(start=0, stop=10),
        ),
        PreviewConfig(
            angles=PreviewDimConfig(start=0, stop=180),
            detector_y=PreviewDimConfig(start=0, stop=128),
            detector_x=PreviewDimConfig(start=10, stop=20),
        ),
    ],
    ids=[
        "no_cropping",
        "crop_det_y_start_0",
        "crop_det_y_start_10",
        "crop_det_x_start_0",
        "crop_det_x_start_10",
    ],
)
def test_standard_tomo_loader_read_block_single_proc(
    standard_data_path: str,
    standard_image_key_path: str,
    preview_config: PreviewConfig,
):
    IN_FILE_PATH = Path(__file__).parent.parent / "test_data/tomo_standard.nxs"
    DARKS_FLATS_CONFIG = DarksFlatsFileConfig(
        file=IN_FILE_PATH,
        data_path=standard_data_path,
        image_key_path=standard_image_key_path,
    )
    ANGLES_CONFIG = RawAngles(data_path="/entry1/tomo_entry/data/rotation_angle")
    SLICING_DIM = 0
    COMM = MPI.COMM_WORLD

    BLOCK_START = 2
    BLOCK_LENGTH = 4
    PROJS_START = 0
    expected_block_shape = (
        BLOCK_LENGTH,
        preview_config.detector_y.stop - preview_config.detector_y.start,
        preview_config.detector_x.stop - preview_config.detector_x.start,
    )
    # Index of block relative to the chunk it belongs to
    EXPECTED_CHUNK_INDEX = (BLOCK_START, 0, 0)
    # Index of block relative to the global data it belongs to (ie, includes chunk shift - for
    # single proc, this is the same as the expected chunk index)
    EXPECTED_BLOCK_GLOBAL_INDEX = (BLOCK_START, 0, 0)

    with mock.patch(
        "httomo.darks_flats.get_darks_flats",
        return_value=(np.zeros(1), np.zeros(1)),
    ):
        loader = StandardTomoLoader(
            in_file=IN_FILE_PATH,
            data_path=DARKS_FLATS_CONFIG.data_path,
            image_key_path=DARKS_FLATS_CONFIG.image_key_path,
            darks=DARKS_FLATS_CONFIG,
            flats=DARKS_FLATS_CONFIG,
            angles=ANGLES_CONFIG,
            preview_config=preview_config,
            slicing_dim=SLICING_DIM,
            comm=COMM,
        )

    block = loader.read_block(BLOCK_START, BLOCK_LENGTH)

    with h5py.File(IN_FILE_PATH, "r") as f:
        dataset: h5py.Dataset = f[standard_data_path]
        projs: np.ndarray = dataset[
            PROJS_START + BLOCK_START : PROJS_START + BLOCK_START + BLOCK_LENGTH,
            preview_config.detector_y.start : preview_config.detector_y.stop,
            preview_config.detector_x.start : preview_config.detector_x.stop,
        ]

    assert block.global_index == EXPECTED_BLOCK_GLOBAL_INDEX
    assert block.chunk_index == EXPECTED_CHUNK_INDEX
    assert block.data.shape == expected_block_shape
    np.testing.assert_array_equal(block.data, projs)


@pytest.mark.mpi
@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2, reason="Only rank-2 MPI is supported with this test"
)
@pytest.mark.parametrize(
    "preview_config",
    [
        PreviewConfig(
            angles=PreviewDimConfig(start=0, stop=180),
            detector_y=PreviewDimConfig(start=0, stop=128),
            detector_x=PreviewDimConfig(start=0, stop=160),
        ),
        PreviewConfig(
            angles=PreviewDimConfig(start=0, stop=180),
            detector_y=PreviewDimConfig(start=0, stop=10),
            detector_x=PreviewDimConfig(start=0, stop=160),
        ),
        PreviewConfig(
            angles=PreviewDimConfig(start=0, stop=180),
            detector_y=PreviewDimConfig(start=10, stop=20),
            detector_x=PreviewDimConfig(start=0, stop=160),
        ),
        PreviewConfig(
            angles=PreviewDimConfig(start=0, stop=180),
            detector_y=PreviewDimConfig(start=0, stop=128),
            detector_x=PreviewDimConfig(start=0, stop=10),
        ),
        PreviewConfig(
            angles=PreviewDimConfig(start=0, stop=180),
            detector_y=PreviewDimConfig(start=0, stop=128),
            detector_x=PreviewDimConfig(start=10, stop=20),
        ),
    ],
    ids=[
        "no_cropping",
        "crop_det_y_start_0",
        "crop_det_y_start_10",
        "crop_det_x_start_0",
        "crop_det_x_start_10",
    ],
)
def test_standard_tomo_loader_read_block_two_procs(
    standard_data_path: str,
    standard_image_key_path: str,
    preview_config: PreviewConfig,
):
    IN_FILE_PATH = Path(__file__).parent.parent / "test_data/tomo_standard.nxs"
    DARKS_FLATS_CONFIG = DarksFlatsFileConfig(
        file=IN_FILE_PATH,
        data_path=standard_data_path,
        image_key_path=standard_image_key_path,
    )
    ANGLES_CONFIG = RawAngles(data_path="/entry1/tomo_entry/data/rotation_angle")
    SLICING_DIM = 0
    COMM = MPI.COMM_WORLD

    BLOCK_START = 2
    BLOCK_LENGTH = 4
    expected_block_shape = (
        BLOCK_LENGTH,
        preview_config.detector_y.stop - preview_config.detector_y.start,
        preview_config.detector_x.stop - preview_config.detector_x.start,
    )
    DATA_SHAPE = (180, 128, 160)

    with mock.patch(
        "httomo.darks_flats.get_darks_flats",
        return_value=(np.zeros(1), np.zeros(1)),
    ):
        loader = StandardTomoLoader(
            in_file=IN_FILE_PATH,
            data_path=DARKS_FLATS_CONFIG.data_path,
            image_key_path=DARKS_FLATS_CONFIG.image_key_path,
            darks=DARKS_FLATS_CONFIG,
            flats=DARKS_FLATS_CONFIG,
            angles=ANGLES_CONFIG,
            preview_config=preview_config,
            slicing_dim=SLICING_DIM,
            comm=COMM,
        )

    block = loader.read_block(BLOCK_START, BLOCK_LENGTH)

    projs_start = (
        preview_config.angles.start
        if COMM.rank == 0
        else (preview_config.angles.stop - preview_config.angles.start) // 2
    )
    # Index of block relative to the chunk it belongs to
    expected_chunk_index = (BLOCK_START, 0, 0)
    # Index of block relative to the global data it belongs to (ie, includes chunk shift - this
    # will differ across two procs)
    expected_block_global_index = (
        (BLOCK_START, 0, 0)
        if COMM.rank == 0
        else (DATA_SHAPE[0] // 2 + BLOCK_START, 0, 0)
    )

    with h5py.File(IN_FILE_PATH, "r") as f:
        dataset: h5py.Dataset = f[standard_data_path]
        projs: np.ndarray = dataset[
            projs_start + BLOCK_START : projs_start + BLOCK_START + BLOCK_LENGTH,
            preview_config.detector_y.start : preview_config.detector_y.stop,
            preview_config.detector_x.start : preview_config.detector_x.stop,
        ]

    assert block.global_index == expected_block_global_index
    assert block.chunk_index == expected_chunk_index
    assert block.data.shape == expected_block_shape
    np.testing.assert_array_equal(block.data, projs)


def test_standard_tomo_loader_read_block_adjust_for_darks_flats_single_proc():
    IN_FILE_PATH = Path(__file__).parent.parent / "test_data/k11_diad/k11-18014.nxs"
    DATA_PATH = "/entry/imaging/data"
    IMAGE_KEY_PATH = "/entry/instrument/imaging/image_key"
    ANGLES_CONFIG = RawAngles(data_path="/entry/imaging_sum/gts_theta_value")
    DARKS_CONFIG = FLATS_CONFIG = DarksFlatsFileConfig(
        file=IN_FILE_PATH,
        data_path=DATA_PATH,
        image_key_path=IMAGE_KEY_PATH,
    )
    PREVIEW_CONFIG = PreviewConfig(
        angles=PreviewDimConfig(start=0, stop=3201),
        detector_y=PreviewDimConfig(start=0, stop=22),
        detector_x=PreviewDimConfig(start=0, stop=26),
    )
    SLICING_DIM = 0
    COMM = MPI.COMM_WORLD

    with mock.patch(
        "httomo.darks_flats.get_darks_flats",
        return_value=(np.zeros(1), np.zeros(1)),
    ):
        loader = StandardTomoLoader(
            in_file=IN_FILE_PATH,
            data_path=DATA_PATH,
            image_key_path=IMAGE_KEY_PATH,
            darks=DARKS_CONFIG,
            flats=FLATS_CONFIG,
            angles=ANGLES_CONFIG,
            preview_config=PREVIEW_CONFIG,
            slicing_dim=SLICING_DIM,
            comm=COMM,
        )

    BLOCK_START = 0
    BLOCK_LENGTH = 4
    EXPECTED_BLOCK_GLOBAL_INDEX = (BLOCK_START, 0, 0)
    block = loader.read_block(BLOCK_START, BLOCK_LENGTH)

    # Darks/flats are at indices 0 to 99 (and 3101 to 3200), projection data starts at index
    # 100
    PROJS_START = 100
    # Index of block relative to the chunk it belongs to
    expected_chunk_index = (BLOCK_START, 0, 0)

    with h5py.File(IN_FILE_PATH, "r") as f:
        dataset: h5py.Dataset = f[DATA_PATH]
        projs: np.ndarray = dataset[
            PROJS_START + BLOCK_START : PROJS_START + BLOCK_START + BLOCK_LENGTH
        ]

    assert block.global_index == EXPECTED_BLOCK_GLOBAL_INDEX
    assert block.chunk_index == expected_chunk_index
    assert block.data.shape[SLICING_DIM] == BLOCK_LENGTH
    np.testing.assert_array_equal(block.data, projs)


@pytest.mark.mpi
@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2, reason="Only rank-2 MPI is supported with this test"
)
def test_standard_tomo_loader_read_block_adjust_for_darks_flats_two_procs():
    IN_FILE_PATH = Path(__file__).parent.parent / "test_data/k11_diad/k11-18014.nxs"
    DATA_PATH = "/entry/imaging/data"
    IMAGE_KEY_PATH = "/entry/instrument/imaging/image_key"
    ANGLES_CONFIG = RawAngles(data_path="/entry/imaging_sum/gts_theta_value")
    DARKS_CONFIG = FLATS_CONFIG = DarksFlatsFileConfig(
        file=IN_FILE_PATH,
        data_path=DATA_PATH,
        image_key_path=IMAGE_KEY_PATH,
    )
    PREVIEW_CONFIG = PreviewConfig(
        angles=PreviewDimConfig(start=0, stop=3201),
        detector_y=PreviewDimConfig(start=0, stop=22),
        detector_x=PreviewDimConfig(start=0, stop=26),
    )
    SLICING_DIM = 0
    COMM = MPI.COMM_WORLD

    with mock.patch(
        "httomo.darks_flats.get_darks_flats",
        return_value=(np.zeros(1), np.zeros(1)),
    ):
        loader = StandardTomoLoader(
            in_file=IN_FILE_PATH,
            data_path=DATA_PATH,
            image_key_path=IMAGE_KEY_PATH,
            darks=DARKS_CONFIG,
            flats=FLATS_CONFIG,
            angles=ANGLES_CONFIG,
            preview_config=PREVIEW_CONFIG,
            slicing_dim=SLICING_DIM,
            comm=COMM,
        )

    BLOCK_START = 2
    BLOCK_LENGTH = 4
    block = loader.read_block(BLOCK_START, BLOCK_LENGTH)

    DATA_SHAPE = (3000, 22, 26)
    CHUNK_SHAPE = (
        DATA_SHAPE[0] // 2,
        DATA_SHAPE[1],
        DATA_SHAPE[2],
    )

    # Darks/flats are at indices 0 to 99 (and 3101 to 3200), projection data starts at index
    # 100
    PROJS_SHIFT = 100
    projs_start = PROJS_SHIFT if COMM.rank == 0 else PROJS_SHIFT + CHUNK_SHAPE[0]
    # Index of block relative to the chunk it belongs to
    expected_chunk_index = (BLOCK_START, 0, 0)
    # Index of block relative to the global data it belongs to (ie, includes chunk shift - this
    # will differ across two procs)
    expected_block_global_index = (
        (BLOCK_START, 0, 0)
        if COMM.rank == 0
        else (DATA_SHAPE[0] // 2 + BLOCK_START, 0, 0)
    )

    with h5py.File(IN_FILE_PATH, "r") as f:
        dataset: h5py.Dataset = f[DATA_PATH]
        projs: np.ndarray = dataset[
            projs_start + BLOCK_START : projs_start + BLOCK_START + BLOCK_LENGTH
        ]

    assert block.global_index == expected_block_global_index
    assert block.chunk_index == expected_chunk_index
    assert block.data.shape[SLICING_DIM] == BLOCK_LENGTH
    np.testing.assert_array_equal(block.data, projs)


def test_standard_tomo_loader_generates_block_with_angles():
    IN_FILE_PATH = Path(__file__).parent.parent / "test_data/tomo_standard.nxs"
    ANGLES_PATH = "/entry1/tomo_entry/data/rotation_angle"
    BLOCK_START = 0
    BLOCK_LENGTH = 2

    with mock.patch(
        "httomo.darks_flats.get_darks_flats",
        return_value=(np.zeros(1), np.zeros(1)),
    ):
        loader = make_standard_tomo_loader()

    block = loader.read_block(BLOCK_START, BLOCK_LENGTH)

    with h5py.File(IN_FILE_PATH, "r") as f:
        dataset: h5py.Dataset = f[ANGLES_PATH]
        angles = np.deg2rad(dataset[...])

    np.testing.assert_array_equal(block.angles, angles)


def test_standard_tomo_loader_user_defined_angles(
    standard_data_path: str,
    standard_image_key_path: str,
    standard_data_darks_flats_config: DarksFlatsFileConfig,
):
    PREVIEW_CONFIG = PreviewConfig(
        angles=PreviewDimConfig(start=0, stop=180),
        detector_y=PreviewDimConfig(start=0, stop=128),
        detector_x=PreviewDimConfig(start=0, stop=160),
    )
    SLICING_DIM = 0
    COMM = MPI.COMM_WORLD
    # Override angles in raw data with the config for some arbitrary array
    USER_DEFINED_ANGLES = UserDefinedAngles(
        start_angle=0,
        stop_angle=180,
        angles_total=720,
    )
    EXPECTED_ANGLES = np.deg2rad(np.linspace(
        USER_DEFINED_ANGLES.start_angle,
        USER_DEFINED_ANGLES.stop_angle,
        USER_DEFINED_ANGLES.angles_total,
    ))

    with mock.patch(
        "httomo.darks_flats.get_darks_flats",
        return_value=(np.zeros(1), np.zeros(1)),
    ):
        loader = StandardTomoLoader(
            in_file=Path(__file__).parent.parent / "test_data/tomo_standard.nxs",
            data_path=standard_data_path,
            image_key_path=standard_image_key_path,
            darks=standard_data_darks_flats_config,
            flats=standard_data_darks_flats_config,
            preview_config=PREVIEW_CONFIG,
            angles=USER_DEFINED_ANGLES,
            slicing_dim=SLICING_DIM,
            comm=COMM,
        )

    BLOCK_START = 0
    BLOCK_LENGTH = 2
    block = loader.read_block(BLOCK_START, BLOCK_LENGTH)
    np.testing.assert_array_equal(block.angles, EXPECTED_ANGLES)


def test_standard_tomo_loader_closes_file(mocker: MockerFixture):
    with mock.patch(
        "httomo.darks_flats.get_darks_flats",
        return_value=(np.zeros(1), np.zeros(1)),
    ):
        loader = make_standard_tomo_loader()

    file_close = mocker.patch.object(loader._h5file, "close")
    loader.finalize()
    file_close.assert_called_once()


def test_standard_tomo_loader_raises_error_slicing_dim(
    standard_data_darks_flats_config: DarksFlatsFileConfig,
):
    IN_FILE_PATH = Path(__file__).parent.parent / "test_data/tomo_standard.nxs"
    ANGLES_CONFIG = RawAngles(data_path="/entry1/tomo_entry/data/rotation_angle")
    PREVIEW_CONFIG = PreviewConfig(
        angles=PreviewDimConfig(start=0, stop=180),
        detector_y=PreviewDimConfig(start=0, stop=128),
        detector_x=PreviewDimConfig(start=0, stop=160),
    )
    SLICING_DIM = 1
    COMM = MPI.COMM_WORLD

    with (
        mock.patch(
            "httomo.darks_flats.get_darks_flats",
            return_value=(np.zeros(1), np.zeros(1)),
        ),
        pytest.raises(NotImplementedError),
    ):
        _ = StandardTomoLoader(
            in_file=IN_FILE_PATH,
            data_path=standard_data_darks_flats_config.data_path,
            image_key_path=standard_data_darks_flats_config.image_key_path,
            darks=standard_data_darks_flats_config,
            flats=standard_data_darks_flats_config,
            preview_config=PREVIEW_CONFIG,
            angles=ANGLES_CONFIG,
            slicing_dim=SLICING_DIM,
            comm=COMM,
        )
