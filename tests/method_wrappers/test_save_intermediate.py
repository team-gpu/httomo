from pathlib import Path
from pytest_mock import MockerFixture
from httomo.method_wrappers import make_method_wrapper
from httomo.method_wrappers.save_intermediate import SaveIntermediateFilesWrapper

from httomo.runner.dataset import DataSet, DataSetBlock
import h5py
from mpi4py import MPI
from httomo.runner.loader import LoaderInterface
from httomo.runner.method_wrapper import MethodWrapper
from tests.testing_utils import make_mock_repo


def test_save_intermediate(
    mocker: MockerFixture, dummy_dataset: DataSet, tmp_path: Path
):
    loader: LoaderInterface = mocker.create_autospec(
        LoaderInterface, instance=True, detector_x=10, detector_y=20
    )

    class FakeModule:
        def save_intermediate_data(
            block, file: h5py.File, path: str, detector_x: int, detector_y: int
        ):
            assert Path(file.filename).name == "task1-testpackage-testmethod-XXX.h5"
            assert detector_x == 10
            assert detector_y == 20
            assert path == "/data"

    mocker.patch("importlib.import_module", return_value=FakeModule)
    prev_method = mocker.create_autospec(
        MethodWrapper,
        instance=True,
        task_id="task1",
        package_name="testpackage",
        method_name="testmethod",
        recon_algorithm="XXX",
    )
    wrp = make_method_wrapper(
        make_mock_repo(mocker, implementation="gpu_cupy"),
        "httomo.methods",
        "save_intermediate_data",
        MPI.COMM_WORLD,
        loader=loader,
        out_dir=tmp_path,
        prev_method=prev_method,
    )
    assert isinstance(wrp, SaveIntermediateFilesWrapper)
    block = dummy_dataset.make_block(0)
    res = wrp.execute(block)

    assert res == block
