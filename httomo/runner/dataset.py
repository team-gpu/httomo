from typing import Optional, Tuple, Union
from typing_extensions import TypeAlias
from httomo.utils import gpu_enabled, xp
import numpy as np


class DataSet:
    """Holds the dataset the methods work on, handling both CPU or GPU.
    It handles the transfers if needed internally, given the currently-active
    GPU device in the CuPy context.

    Flats, darks, and angles are assumed to be read-only - separate copies on
    CPU and GPU are maintained as needed. Depending on where data itself is,
    the flats/darks/angles will be returned on the same device (and cached).

    Example::

       dataset = DataSet(data, angles, flats, darks)
       dataset.data        # access data
       dataset.to_gpu()    # transfer
       dataset.data        # now returns a GPU-based array
       assert dataset.is_gpu is True
    """

    generic_array: TypeAlias = Union[xp.ndarray, np.ndarray]

    def __init__(
        self,
        data: generic_array,
        angles: np.ndarray,
        flats: np.ndarray,
        darks: np.ndarray,
        global_shape: Optional[Tuple[int, int, int]] = None,
        global_index: Tuple[int, int, int] = (0, 0, 0),
    ):
        self._angles = angles
        self._flats = flats
        self._darks = darks
        self._data = data

        if global_shape is None:
            self._global_shape = data.shape
        elif any(i < d for i, d in zip(global_shape, data.shape)):
            raise ValueError(
                f"A global shape of {global_shape} is incompatible with a local shape {data.shape}"
            )
        else:
            self._global_shape = global_shape
        self._global_index = global_index

        self.lock()
        if gpu_enabled:
            import cupy as cp

            # cached GPU data - transferred lazily
            self._flats_gpu: Optional[cp.ndarray] = None
            self._darks_gpu: Optional[cp.ndarray] = None
            # keep track if fields have been reset on GPU, to ensure
            # transferring back to CPU if needed
            self._flats_dirty: bool = False
            self._darks_dirty: bool = False

    @property
    def global_shape(self) -> Tuple[int, int, int]:
        """Overall shape of the data, regardless of chunking and blocking"""
        return self._global_shape

    @property
    def shape(self) -> Tuple[int, int, int]:
        """Shape of this part of the dataset"""
        return self._data.shape

    @property
    def global_index(self) -> Tuple[int, int, int]:
        """The starting indices in all 3 dimensions of this data block within the
        global data."""
        return self._global_index

    @property
    def chunk_index(self) -> Tuple[int, int, int]:
        """The index of this dataset within the chunk handled by the current process"""
        return (0, 0, 0)

    @property
    def chunk_shape(self) -> Tuple[int, int, int]:
        """Shape of the full chunk handled by the current process"""
        return self.shape

    @property
    def is_last_in_chunk(self) -> bool:
        """Check if the current dataset is the final one for the chunk handled by the current process"""
        return True

    @property
    def angles(self) -> np.ndarray:
        return self._get_value("angles")

    @angles.setter
    def angles(self, new_data: np.ndarray):
        self._set_value("angles", new_data)

    @property
    def angles_radians(self) -> np.ndarray:
        """Alias for angles"""
        return self.angles

    @angles_radians.setter
    def angles_radians(self, new_data: np.ndarray):
        """Alias setter for angles"""
        self.angles = new_data

    @property
    def darks(self) -> generic_array:
        return self._get_value("darks")

    @darks.setter
    def darks(self, new_data: generic_array):
        self._set_value("darks", new_data)

    @property
    def dark(self) -> generic_array:
        """Alias for darks"""
        return self.darks

    @dark.setter
    def dark(self, new_data: generic_array):
        self.darks = new_data

    @property
    def flats(self) -> generic_array:
        return self._get_value("flats")

    @flats.setter
    def flats(self, new_data: generic_array):
        self._set_value("flats", new_data)

    @property
    def flat(self) -> generic_array:
        """Alias for flats"""
        return self.flats

    @flat.setter
    def flat(self, new_data: generic_array):
        self.flats = new_data

    @property
    def data(self) -> generic_array:
        return self._data

    @data.setter
    def data(self, new_data: generic_array):
        self._data = new_data
        self._chunk_shape = new_data.shape

    def get_data_block(
        self, start0: int, stop0: int, start1: int, stop1: int, start2: int, stop2: int
    ) -> generic_array:
        return self._data[start0:stop0, start1:stop1, start2:stop2]

    def set_data_block(self, start_idx: Tuple[int, int, int], new_data: generic_array):
        self._data[
            start_idx[0] : start_idx[0] + new_data.shape[0],
            start_idx[1] : start_idx[1] + new_data.shape[1],
            start_idx[2] : start_idx[2] + new_data.shape[2],
        ] = new_data

    @property
    def is_gpu(self) -> bool:
        """Check if arrays are currently residing on GPU"""
        return getattr(self._data, "device", None) is not None

    @property
    def is_cpu(self) -> bool:
        """Check if arrays are currently residing on CPU"""
        return not self.is_gpu
    
    @property
    def is_full(self) -> bool:
        """Check if the dataset is the full global data"""
        return False


    def lock(self):
        """Makes angles, darks and flats read-only, to avoid coding errors.
        Note: this is the default in the constructor - only the the data array is writable
        Also note that this is only supported for the numpy arrays - gpu arrays can't be locked
        """
        self._angles.setflags(write=False)
        self._darks.setflags(write=False)
        self._flats.setflags(write=False)
        self._is_locked = True

    def unlock(self):
        """Unlock the read-only flag for the darks, angles, and flats members,
        allowing to overwrite them with the setter or modify their values"""
        self._angles.setflags(write=True)
        self._darks.setflags(write=True)
        self._flats.setflags(write=True)
        self._is_locked = False

    @property
    def is_locked(self) -> bool:
        return self._is_locked

    def to_gpu(self):
        """Transfer dataset to GPU if not already."""
        if not gpu_enabled:
            raise ValueError("cannot transfer to GPU if not enabled")
        if not self.is_gpu:
            self._data = xp.asarray(self.data)

    def to_cpu(self):
        """Transfter dataset to CPU (if not already)"""
        if not self.is_gpu:
            return
        self._data = xp.asnumpy(self._data)

    def make_block(self, dim: int, start: int = 0, length: Optional[int] = None):
        """Create a block from this dataset, which slices in dimension `dim`
        starting at index `start`, and taking `length` elements (if it's not given,
        it uses the remaining length of the block after `start`).

        The returned block is a `DataSet` object itself, but it references the
        original one for the darks/flats/angles arrays and re-use the GPU-cached
        version of those if needed."""
        if length is None:
            length = self.chunk_shape[dim] - start
        return DataSetBlock(self, dim, start, length)

    @property
    def is_block(self) -> bool:
        """Check if this DataSet is a block (output of `make_block`)"""
        return False

    def __dir__(self) -> list[str]:
        """Return only those properties that are relevant for the data"""
        return ["data", "angles", "angles_radians", "darks", "flats", "dark", "flat"]

    ###### internal helpers ######

    def _get_value(
        self, field: str, data_is_gpu: Optional[bool] = None
    ) -> generic_array:
        """Helper function to get a field from this object.
        It uses getattr/setattr a lot, to allow for re-use from all the getters.

        `data_is_gpu` can be used to tell this method to assume the data array
        is on GPU or not - it will be used instead of self.is_gpu if given"""

        # angles always stay on CPU
        if field == "angles":
            return getattr(self, f"_{field}")

        is_gpu = data_is_gpu if data_is_gpu is not None else self.is_gpu
        if is_gpu:
            setattr(
                self,
                f"_{field}_gpu",
                self._transfer_if_needed(
                    getattr(self, f"_{field}"), getattr(self, f"_{field}_gpu")
                ),
            )
            return getattr(self, f"_{field}_gpu")
        if gpu_enabled and getattr(self, f"_{field}_dirty"):
            setattr(self, f"_{field}", xp.asnumpy(getattr(self, f"_{field}_gpu")))
            setattr(self, f"_{field}_dirty", False)
        return getattr(self, f"_{field}")

    def _set_value(self, field: str, new_data: generic_array):
        """Sets a value of a field in this object, only if unlocked.
        It is a helper used in the setters for darks, flats, angles"""
        if self.is_locked:
            raise ValueError(f"attempt to reset {field} in a locked dataset")
        if not gpu_enabled or field == "angles":
            assert (
                getattr(new_data, "device", None) is None
            ), f"GPU array for CPU-only field {field}"
            setattr(self, f"_{field}", new_data)
            return
        if getattr(new_data, "device", None) is not None:
            # got GPU data - mark CPU dirty
            setattr(self, f"_{field}_gpu", new_data)
            setattr(self, f"_{field}_dirty", True)
        else:
            # got CPU data - make sure we remove cached GPU array
            setattr(self, f"_{field}_gpu", None)
            setattr(self, f"_{field}", new_data)

    def _transfer_if_needed(self, cpuarray: np.ndarray, gpuarray: Optional[xp.ndarray]):
        """Internal helper to transfer flats/darks/angles lazily"""
        if gpuarray is None:
            gpuarray = xp.asarray(cpuarray)
        assert (
            gpuarray.device.id == xp.cuda.Device().id
        ), f"GPU array is on a different GPU (expected: {xp.cuda.Device().id}, actual: {gpuarray.device.id})"
        return gpuarray


class DataSetBlock(DataSet):
    """Represents a slice/block of a dataset, as returned returned by `make_block`
    in a DataSet object. It is a DataSet (inherits from it) and users can mostly
    ignore the fact that it's just a view.

    It stores the base object internally and routes all calls for the auxilliary
    arrays to the base object (darks/flats/angles). It does not store these directly.
    """

    def __init__(self, base: DataSet, dim: int, start: int, length: int):
        idx_expr = [(0, base.shape[0]), (0, base.shape[1]), (0, base.shape[2])]
        idx_expr[dim] = (start, start + length)
        global_index = list(base.global_index)
        global_index[dim] += start
        # we pass an empty size-0 array to base class, as we're not going to use these
        # fields anyway here (we access the originals via self._base)
        super().__init__(
            data=base.get_data_block(
                idx_expr[0][0],
                idx_expr[0][1],
                idx_expr[1][0],
                idx_expr[1][1],
                idx_expr[2][0],
                idx_expr[2][1],
            ),
            flats=np.empty((0,)),
            darks=np.empty((0,)),
            angles=np.empty((0,)),
            global_shape=base.global_shape,
            global_index=(global_index[0], global_index[1], global_index[2]),
        )
        self._base = base
        idx = [0, 0, 0]
        idx[dim] = start
        self._chunk_index = (idx[0], idx[1], idx[2])
        self._dim = dim

    @property
    def is_block(self) -> bool:
        return True
    
    @property
    def is_full(self) -> bool:
        """Check if the dataset is the full global data"""
        return False


    @property
    def chunk_index(self) -> Tuple[int, int, int]:
        """The index of this dataset within the chunk handled by the current process"""
        return self._chunk_index

    @property
    def chunk_shape(self) -> Tuple[int, int, int]:
        """Shape of the full chunk handled by the current process"""
        return self._base.chunk_shape

    @property
    def is_last_in_chunk(self) -> bool:
        """Check if the current dataset is the final one for the chunk handled by the current process"""
        return (
            self.chunk_index[self._dim] + self.shape[self._dim]
            == self.chunk_shape[self._dim]
        )

    @property
    def base(self) -> DataSet:
        """Get the original (unblocked) dataset"""
        return self._base

    def _set_value(self, field: str, new_data: DataSet.generic_array):
        raise ValueError(f"Cannot update field {field} in a block/slice dataset")

    def _get_value(
        self, field: str, is_gpu: Optional[bool] = None
    ) -> DataSet.generic_array:
        return self._base._get_value(field, self.is_gpu if is_gpu is None else is_gpu)

    def make_block(self, dim: int, start: int = 0, length: Optional[int] = None):
        raise ValueError("Cannot slice a dataset that is already a slice")


class FullFileDataSet(DataSet):
    generic_array = DataSet.generic_array

    def __init__(
        self,
        data: np.ndarray,
        angles: np.ndarray,
        flats: np.ndarray,
        darks: np.ndarray,
        global_index: Tuple[int, int, int],
        chunk_shape: Tuple[int, int, int],
    ):
        super().__init__(
            data,
            angles,
            flats,
            darks,
            (data.shape[0], data.shape[1], data.shape[2]),
            global_index,
        )
        self._chunk_shape = chunk_shape

    @property
    def shape(self) -> Tuple[int, int, int]:
        return self._global_shape

    @property
    def chunk_shape(self) -> Tuple[int, int, int]:
        return self._chunk_shape
    
    @property
    def is_full(self) -> bool:
        return True

    @property
    def data(self) -> DataSet.generic_array:
        # Note: this view doesn't allow write-back, it's a copy of the data in the file
        return self._data[
            self._global_index[0] : self._global_index[0] + self._chunk_shape[0],
            self._global_index[1] : self._global_index[1] + self._chunk_shape[1],
            self._global_index[2] : self._global_index[2] + self._chunk_shape[2],
        ]

    @data.setter
    def data(self, new_data: DataSet.generic_array):
        self.set_data_block((0, 0, 0), new_data)

    def set_data_block(
        self, start_idx: Tuple[int, int, int], new_data: DataSet.generic_array
    ):
        if any(
            start + length > self._chunk_shape[i]
            for i, (start, length) in enumerate(zip(start_idx, new_data.shape))
        ):
            raise ValueError(
                "in a FullFileDataSet, changing shape of a chunk is not allowed"
            )
        if self._data.dtype != new_data.dtype:
            raise ValueError(
                "in a FullFileDataSet, changing the datatype is not allowed"
            )
        if getattr(new_data, "device", None) is not None:
            new_data = xp.asnumpy(new_data)

        self._data[
            self._global_index[0]
            + start_idx[0] : self._global_index[0]
            + start_idx[0]
            + new_data.shape[0],
            self._global_index[1]
            + start_idx[1] : self._global_index[1]
            + start_idx[1]
            + new_data.shape[1],
            self._global_index[2]
            + start_idx[2] : self._global_index[2]
            + start_idx[2]
            + new_data.shape[2],
        ] = new_data

    def get_data_block(
        self, start0: int, stop0: int, start1: int, stop1: int, start2: int, stop2: int
    ) -> DataSet.generic_array:
        start0 += self._global_index[0]
        stop0 += self._global_index[0]
        start1 += self._global_index[1]
        stop1 += self._global_index[1]
        start2 += self._global_index[2]
        stop2 += self._global_index[2]
        return self._data[start0:stop0, start1:stop1, start2:stop2]
