from typing import Union
import numpy as np
from httomo.method_wrappers import make_method_wrapper
from httomo.method_wrappers.rotation import RotationWrapper
from httomo.runner.dataset import DataSet
from httomo.utils import Pattern, gpu_enabled, xp
from ..testing_utils import make_mock_repo


import pytest
from mpi4py import MPI
from pytest_mock import MockerFixture


def test_rotation_fails_with_projection_method(mocker: MockerFixture):
    class FakeModule:
        def rotation_tester(data, ind=None):
            return 42.0

    mocker.patch("importlib.import_module", return_value=FakeModule)
    with pytest.raises(NotImplementedError):
        make_method_wrapper(
            make_mock_repo(mocker, pattern=Pattern.projection),
            "mocked_module_path.rotation",
            "rotation_tester",
            MPI.COMM_WORLD,
        )


def test_rotation_accumulates_blocks(
    mocker: MockerFixture, dummy_dataset: DataSet
):
    class FakeModule:
        def rotation_tester(data, ind=None):
            assert data.ndim == 2  # for 1 slice only
            np.testing.assert_array_equal(data, dummy_dataset.data[:, 4, :])
            return 42.0

    mocker.patch("importlib.import_module", return_value=FakeModule)
    wrp = make_method_wrapper(
        make_mock_repo(mocker),
        "mocked_module_path.rotation",
        "rotation_tester",
        MPI.COMM_WORLD,
        output_mapping={"cor": "cor"},
    )
    assert isinstance(wrp, RotationWrapper)
    normalize = mocker.patch.object(
        wrp, "normalize_sino", side_effect=lambda sino, flats, darks: sino
    )
    # generate varying numbers so the comparison above works
    dummy_dataset.data = np.arange(dummy_dataset.data.size, dtype=np.float32).reshape(
        dummy_dataset.shape
    )
    b1 = dummy_dataset.make_block(0, 0, dummy_dataset.shape[0] // 2)
    b2 = dummy_dataset.make_block(
        0, dummy_dataset.shape[0] // 2, dummy_dataset.shape[0] // 2
    )
    wrp.execute(b1)
    normalize.assert_not_called()
    wrp.execute(b2)
    normalize.assert_called_once()
    assert wrp.get_side_output() == {"cor": 42.0}


@pytest.mark.parametrize("gpu", [False, True])
@pytest.mark.parametrize("rank", [0, 1])
@pytest.mark.parametrize("ind_par", ["mid", 2, None])
def test_rotation_gathers_single_sino_slice(
    mocker: MockerFixture,
    dummy_dataset: DataSet,
    rank: int,
    ind_par: Union[str, int, None],
    gpu: bool,
):
    class FakeModule:
        def rotation_tester(data, ind=None):
            assert rank == 0  # for rank 1, it shouldn't be called
            assert data.ndim == 2  # for 1 slice only
            assert ind == 0
            if ind_par == "mid" or ind_par is None:
                xp.testing.assert_array_equal(
                    dummy_dataset.data[:, (dummy_dataset.data.shape[1] - 1) // 2, :],
                    data,
                )
            else:
                xp.testing.assert_array_equal(dummy_dataset.data[:, ind_par, :], data)
            return 42.0

    mocker.patch("importlib.import_module", return_value=FakeModule)
    comm = mocker.MagicMock()
    comm.rank = rank
    comm.size = 2
    wrp = make_method_wrapper(
        make_mock_repo(mocker, implementation="gpu_cupy"),
        "mocked_module_path.rotation",
        "rotation_tester",
        comm,
    )
    assert isinstance(wrp, RotationWrapper)
    if ind_par is not None:
        wrp["ind"] = ind_par
    dummy_dataset.data = np.arange(dummy_dataset.data.size, dtype=np.float32).reshape(
        dummy_dataset.shape
    )
    if gpu:
        dummy_dataset.to_gpu()
    mocker.patch.object(wrp, "_gather_sino_slice", side_effect=lambda s: wrp.sino)
    normalize = mocker.patch.object(
        wrp, "normalize_sino", side_effect=lambda sino, f, d: sino
    )
    
    comm.bcast.return_value = 42.0

    res = wrp.execute(dummy_dataset.make_block(0))

    assert wrp.pattern == Pattern.projection
    xp.testing.assert_array_equal(res.data, dummy_dataset.data)
    comm.bcast.assert_called_once()
    if rank == 0:
        normalize.assert_called_once()
    else:
        normalize.assert_not_called()


@pytest.mark.parametrize("rank", [0, 1])
def test_rotation_gather_sino_slice(mocker: MockerFixture, rank: int):
    class FakeModule:
        def rotation_tester(data, ind=None):
            return 42.0

    mocker.patch("importlib.import_module", return_value=FakeModule)
    comm = mocker.MagicMock()
    comm.rank = rank
    comm.size = 2
    wrp = make_method_wrapper(
        make_mock_repo(mocker),
        "mocked_module_path.rotation",
        "rotation_tester",
        comm,
    )
    assert isinstance(wrp, RotationWrapper)
    if rank == 0:
        wrp.sino = np.arange(2 * 6, dtype=np.float32).reshape((2, 6))
    else:
        wrp.sino = np.arange(2 * 6, 5 * 6, dtype=np.float32).reshape((3, 6))
    
    if rank == 0:
        comm.gather.return_value = [2 * 6, 3 * 6]
    else:
        comm.gather.return_value = [2 * 6]

    res = wrp._gather_sino_slice((5, 13, 6))

    comm.Gatherv.assert_called_once()
    if rank == 0:
        assert res.shape == (5, 6)
        comm.gather.assert_called_once_with(2 * 6)
    else:
        assert res is None
        comm.gather.assert_called_once_with(3 * 6)


def test_rotation_normalize_sino_no_darks_flats():
    ret = RotationWrapper.normalize_sino(
        np.ones((10, 10), dtype=np.float32), None, None
    )

    assert ret.shape == (10, 1, 10)
    np.testing.assert_allclose(np.squeeze(ret), 1.0)


def test_rotation_normalize_sino_same_darks_flats():
    ret = RotationWrapper.normalize_sino(
        np.ones((10, 10), dtype=np.float32),
        0.5
        * np.ones(
            (
                10,
                10,
            ),
            dtype=np.float32,
        ),
        0.5
        * np.ones(
            (
                10,
                10,
            ),
            dtype=np.float32,
        ),
    )

    assert ret.shape == (10, 1, 10)
    np.testing.assert_allclose(ret, 0.5)


def test_rotation_normalize_sino_scalar():
    ret = RotationWrapper.normalize_sino(
        np.ones((10, 10), dtype=np.float32),
        0.5
        * np.ones(
            (
                10,
                10,
            ),
            dtype=np.float32,
        ),
        0.5
        * np.ones(
            (
                10,
                10,
            ),
            dtype=np.float32,
        ),
    )

    assert ret.shape == (10, 1, 10)
    np.testing.assert_allclose(ret, 0.5)


def test_rotation_normalize_sino_different_darks_flats():
    ret = RotationWrapper.normalize_sino(
        2.0 * np.ones((10, 10), dtype=np.float32),
        1.0 * np.ones((10, 10), dtype=np.float32),
        0.5 * np.ones((10, 10), dtype=np.float32),
    )

    assert ret.shape == (10, 1, 10)
    np.testing.assert_allclose(np.squeeze(ret), 1.0)


@pytest.mark.skipif(
    not gpu_enabled or xp.cuda.runtime.getDeviceCount() == 0,
    reason="skipped as cupy is not available",
)
@pytest.mark.cupy
def test_rotation_normalize_sino_different_darks_flats_gpu():
    ret = RotationWrapper.normalize_sino(
        2.0 * xp.ones((10, 10), dtype=np.float32),
        1.0 * xp.ones((10, 10), dtype=np.float32),
        0.5 * xp.ones((10, 10), dtype=np.float32),
    )

    assert ret.shape == (10, 1, 10)
    assert getattr(ret, "device", None) is not None
    xp.testing.assert_allclose(xp.squeeze(ret), 1.0)


def test_rotation_180(mocker: MockerFixture, dummy_dataset: DataSet):
    class FakeModule:
        def rotation_tester(data, ind):
            return 42.0  # center of rotation

    mocker.patch("importlib.import_module", return_value=FakeModule)
    wrp = make_method_wrapper(
        make_mock_repo(mocker),
        "mocked_module_path.rotation",
        "rotation_tester",
        MPI.COMM_WORLD,
        output_mapping={"cor": "center"},
        ind=5,
    )

    block = dummy_dataset.make_block(0)
    new_block = wrp.execute(block)

    assert wrp.get_side_output() == {"center": 42.0}
    assert new_block == block  # note: not a deep comparison


def test_rotation_360(mocker: MockerFixture, dummy_dataset: DataSet):
    class FakeModule:
        def rotation_tester(data, ind):
            # cor, overlap, side, overlap_position - from find_center_360
            return 42.0, 3.0, 1, 10.0

    mocker.patch("importlib.import_module", return_value=FakeModule)
    wrp = make_method_wrapper(
        make_mock_repo(mocker),
        "mocked_module_path.rotation",
        "rotation_tester",
        MPI.COMM_WORLD,
        output_mapping={
            "cor": "center",
            "overlap": "overlap",
            "overlap_position": "pos",
        },
        ind=5,
    )
    block = dummy_dataset.make_block(0)
    new_block = wrp.execute(block)

    assert wrp.get_side_output() == {
        "center": 42.0,
        "overlap": 3.0,
        "pos": 10.0,
    }
    assert new_block == block  # note: not a deep comparison