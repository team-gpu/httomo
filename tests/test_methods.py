from pathlib import Path
from httomo.methods import calculate_stats, save_intermediate_data

import numpy as np
import pytest
from mpi4py import MPI
import h5py
from httomo.runner.auxiliary_data import AuxiliaryData
from httomo.runner.dataset import DataSetBlock

from httomo.utils import gpu_enabled


def test_calculate_stats_simple():
    data = np.arange(30, dtype=np.float32).reshape((2, 3, 5)) - 10.0
    ret = calculate_stats(data)

    assert ret == (-10.0, 19.0, np.sum(data), 30)


def test_calculate_stats_with_nan_and_inf():
    data = np.arange(30, dtype=np.float32).reshape((2, 3, 5)) - 10.0
    expected = np.sum(data) - data[1, 1, 1] - data[0, 2, 3] - data[1, 2, 3]
    data[1, 1, 1] = float("inf")
    data[0, 2, 3] = float("-inf")
    data[1, 2, 3] = float("nan")
    ret = calculate_stats(data)

    assert ret == (-10.0, 19.0, expected, 30)


@pytest.mark.parametrize("gpu", [False, True])
def test_save_intermediate_data( tmp_path: Path, gpu: bool):
    if gpu and not gpu_enabled:
        pytest.skip("No GPU available")

    # use increasing numbers in the data, to make sure blocks have different content
    GLOBAL_SHAPE=(10,10,10)
    global_data = np.arange(np.prod(GLOBAL_SHAPE), dtype=np.float32).reshape(
        GLOBAL_SHAPE
    )
    aux_data = AuxiliaryData(angles=np.ones(GLOBAL_SHAPE[0], dtype=np.float32))
    bsize = 3
    b1 = DataSetBlock(data=global_data[:bsize], aux_data=aux_data,
                      slicing_dim=0,
                      block_start=0,
                      chunk_start=0,
                      chunk_shape=GLOBAL_SHAPE,
                      global_shape=GLOBAL_SHAPE)
    b2 = DataSetBlock(data=global_data[bsize:], aux_data=aux_data,
                      slicing_dim=0,
                      block_start=bsize,
                      chunk_start=0,
                      chunk_shape=GLOBAL_SHAPE,
                      global_shape=GLOBAL_SHAPE)

    if gpu:
        b1.to_gpu()
        b2.to_gpu()

    with h5py.File(
        tmp_path / "test_file.h5", "w", driver="mpio", comm=MPI.COMM_WORLD
    ) as file:
        # save in 2 blocks, starting with the second to confirm order-independence
        save_intermediate_data(
            b2,
            file,
            path="/data",
            detector_x=10,
            detector_y=20,
        )
        save_intermediate_data(
            b1,
            file,
            path="/data",
            detector_x=10,
            detector_y=20,
        )

    with h5py.File(tmp_path / "test_file.h5", "r") as file:
        assert "/data" in file
        data = file["/data"]
        np.testing.assert_array_equal(data, global_data)
        assert "/angles" in file
        angles = file["/angles"]
        np.testing.assert_array_equal(angles, aux_data.get_angles())
        assert "test_file.h5" in file
        np.testing.assert_array_equal(file["test_file.h5"], [0, 0])
        assert "data_dims" in file
        np.testing.assert_array_equal(file["data_dims"]["detector_x_y"], [10, 20])


@pytest.mark.mpi
@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2, reason="Only rank-2 MPI is supported with this test"
)
def test_save_intermediate_data_mpi(tmp_path: Path):
    comm = MPI.COMM_WORLD
    # make sure we use the same tmp_path on both processes
    tmp_path = comm.bcast(tmp_path)
    GLOBAL_SHAPE = (10, 10, 10)
    csize=5
    # use increasing numbers in the data, to make sure blocks have different content
    global_data = np.arange(np.prod(GLOBAL_SHAPE), dtype=np.float32).reshape(
        GLOBAL_SHAPE
    )
    aux_data = AuxiliaryData(angles=np.ones(GLOBAL_SHAPE[0], dtype=np.float32))
    # give each process only a portion of the data
    rank_data = global_data[:csize, :, :] if comm.rank == 0 else global_data[csize:, :, :]
    # create 2 blocks per rank
    b1 = DataSetBlock(
        data=rank_data[:3, :, :],
        aux_data=aux_data,
        slicing_dim=0,
        block_start=0,
        chunk_start=0 if comm.rank == 0 else csize,
        global_shape=GLOBAL_SHAPE,
        chunk_shape=(csize, GLOBAL_SHAPE[1], GLOBAL_SHAPE[2])
    )
    b2 = DataSetBlock(
        data=rank_data[3:, :, :],
        aux_data=aux_data,
        slicing_dim=0,
        block_start=3,
        chunk_start=0 if comm.rank == 0 else csize,
        global_shape=GLOBAL_SHAPE,
        chunk_shape=(csize, GLOBAL_SHAPE[1], GLOBAL_SHAPE[2])
    )

    with h5py.File(tmp_path / "test_file.h5", "w", driver="mpio", comm=comm) as file:
        # save in 2 blocks, starting with the second to confirm order-independence
        save_intermediate_data(
            b2,
            file,
            path="/data",
            detector_x=10,
            detector_y=20,
        )
        save_intermediate_data(
            b1,
            file,
            path="/data",
            detector_x=10,
            detector_y=20,
        )

    # open without MPI, looking at the full file
    with h5py.File(tmp_path / "test_file.h5", "r") as file:
        assert "/data" in file
        data = file["/data"]
        np.testing.assert_array_equal(data, global_data)
        assert "/angles" in file
        angles = file["/angles"]
        np.testing.assert_array_equal(angles, aux_data.get_angles())
        assert "test_file.h5" in file
        np.testing.assert_array_equal(file["test_file.h5"], [0, 0])
        assert "data_dims" in file
        np.testing.assert_array_equal(file["data_dims"]["detector_x_y"], [10, 20])
