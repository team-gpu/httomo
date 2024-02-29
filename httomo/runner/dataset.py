from typing import Optional, Tuple, Union
from typing_extensions import TypeAlias
from httomo.runner.auxiliary_data import AuxiliaryData
from httomo.utils import gpu_enabled, xp
import numpy as np

from httomo.utils import make_3d_shape_from_shape
from httomo.utils import make_3d_shape_from_array


class DataSetBlock:
    """Represents a slice/block of a dataset, as returned returned by `make_block`
    in a DataSet object. It is a DataSet (inherits from it) and users can mostly
    ignore the fact that it's just a view.

    It stores the base object internally and routes all calls for the auxilliary
    arrays to the base object (darks/flats/angles). It does not store these directly.
    """
    
    generic_array: TypeAlias = Union[np.ndarray, xp.ndarray]

    def __init__(
        self,
        data: np.ndarray,
        aux_data: AuxiliaryData,
        slicing_dim: int = 0,
        block_start: int = 0,
        chunk_start: int = 0,
        global_shape: Optional[Tuple[int, int, int]] = None,
        chunk_shape: Optional[Tuple[int, int, int]] = None,
    ):
        self._data = data
        self._aux_data = aux_data
        self._slicing_dim = slicing_dim
        self._block_start = block_start
        self._chunk_start = chunk_start

        if global_shape is None:
            self._global_shape = make_3d_shape_from_array(data)
        else:
            self._global_shape = global_shape
            
        if chunk_shape is None:
            self._chunk_shape = make_3d_shape_from_array(data)
        else:
            self._chunk_shape = chunk_shape

        chunk_index = [0, 0, 0]
        chunk_index[slicing_dim] += block_start
        self._chunk_index = make_3d_shape_from_shape(chunk_index)
        global_index = [0, 0, 0]
        global_index[slicing_dim] += chunk_start + block_start
        self._global_index = make_3d_shape_from_shape(global_index)

        self._check_inconsistencies()
        
    def _check_inconsistencies(self):
        if self.chunk_index[self.slicing_dim] < 0:
            raise ValueError("block start index must be >= 0")
        if self.chunk_index[self.slicing_dim] + self.shape[self.slicing_dim] > self.chunk_shape[self.slicing_dim]:
            raise ValueError("block spans beyond the chunk's boundaries")
        if self.global_index[self.slicing_dim] < 0:
            raise ValueError("chunk start index must be >= 0")
        if self.global_index[self.slicing_dim] + self.shape[self.slicing_dim] > self.global_shape[self.slicing_dim]:
            raise ValueError("chunk spans beyond the global data boundaries")
        if any(self.chunk_shape[i] > self.global_shape[i] for i in range(3)):    
            raise ValueError("chunk shape is larger than the global shape")
        if any(self.shape[i] > self.chunk_shape[i] for i in range(3)):
            raise ValueError("block shape is larger than the chunk shape")
        if any(self.shape[i] != self.global_shape[i] for i in range(3) if i != self.slicing_dim):
            raise ValueError("block shape inconsistent with non-slicing dims of global shape")
        
        assert not any(self.chunk_shape[i] != self.global_shape[i] for i in range(3) if i != self.slicing_dim)
        
        if len(self.angles) < self.global_shape[0]:
            raise ValueError("angles array must be at least as long as projection dimension of the data")
        
    @property
    def aux_data(self) -> AuxiliaryData:
        return self._aux_data
    
    @property
    def shape(self) -> Tuple[int, int, int]:
        """Shape of the data in this block"""
        return make_3d_shape_from_array(self._data)

    @property
    def chunk_index(self) -> Tuple[int, int, int]:
        """The index of this block within the chunk handled by the current process"""
        return self._chunk_index

    @property
    def chunk_shape(self) -> Tuple[int, int, int]:
        """Shape of the full chunk handled by the current process"""
        return self._chunk_shape
    
    @property
    def global_index(self) -> Tuple[int, int, int]:
        """The index of this block within the global data across all processes"""
        return self._global_index

    @property
    def global_shape(self) -> Tuple[int, int, int]:
        """Shape of the global data across all processes"""
        return self._global_shape
    
    @property
    def is_cpu(self) -> bool:
        return getattr(self._data, "device", None) is None
    
    @property
    def is_gpu(self) -> bool:
        return not self.is_cpu
    
    @property
    def angles(self) -> np.ndarray:
        return self._aux_data.get_angles()
    
    @angles.setter
    def angles(self, new_angles: np.ndarray):
        self._aux_data.set_angles(new_angles)
    
    @property
    def angles_radians(self) -> np.ndarray:
        return self.angles
    
    @angles_radians.setter
    def angles_radians(self, new_angles: np.ndarray):
        self.angles = new_angles

    @property
    def is_last_in_chunk(self) -> bool:
        """Check if the current dataset is the final one for the chunk handled by the current process"""
        return (
            self.chunk_index[self._slicing_dim] + self.shape[self._slicing_dim]
            == self.chunk_shape[self._slicing_dim]
        )

    @property
    def slicing_dim(self) -> int:
        return self._slicing_dim
    
    def _empty_aux_array(self):
        empty_shape = list(self._data.shape)
        empty_shape[self.slicing_dim] = 0
        return np.empty_like(self._data, shape=empty_shape)

    @property
    def data(self) -> generic_array:
        return self._data

    @data.setter
    def data(self, new_data: generic_array):
        global_shape = list(self._global_shape)
        chunk_shape = list(self._chunk_shape)
        for i in range(3):
            if i != self.slicing_dim:
                global_shape[i] = new_data.shape[i]
                chunk_shape[i] = new_data.shape[i]
            elif self._data.shape[i] != new_data.shape[i]:
                raise ValueError("shape mismatch in slicing dimension")
                
        self._data = new_data
        self._global_shape = make_3d_shape_from_shape(global_shape)
        self._chunk_shape = make_3d_shape_from_shape(chunk_shape)

    @property
    def darks(self) -> generic_array:
        darks = self._aux_data.get_darks(self.is_gpu)
        if darks is None:
            darks = self._empty_aux_array()
        return darks

    @darks.setter
    def darks(self, darks: generic_array):
        self._aux_data.set_darks(darks)
        
    # alias
    @property
    def dark(self) -> generic_array:
        return self.darks
    
    @dark.setter
    def dark(self, darks: generic_array):
        self.darks = darks
    
    @property
    def flats(self) -> generic_array:
        flats = self._aux_data.get_flats(self.is_gpu)
        if flats is None:
            flats = self._empty_aux_array()
        return flats

    @flats.setter
    def flats(self, flats: generic_array):
        self._aux_data.set_flats(flats)
        
    # alias
    @property
    def flat(self) -> generic_array:
        return self.flats
    
    @flat.setter
    def flat(self, flats: generic_array):
        self.flats = flats

    def to_gpu(self):
        if not gpu_enabled:
            raise ValueError("no GPU available")
        # from doc: if already on GPU, no copy is taken
        self._data = xp.asarray(self.data, order="C")        

    def to_cpu(self):
        if not gpu_enabled:
            return
        self._data = xp.asnumpy(self.data, order="C")
    
    def __dir__(self) -> list[str]:
        """Return only those properties that are relevant for the data"""
        return ["data", "angles", "angles_radians", "darks", "flats", "dark", "flat"]
