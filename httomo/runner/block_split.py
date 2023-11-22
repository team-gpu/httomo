import math
from typing import Iterator
import numpy as np
from httomo.runner.dataset import DataSet
from httomo.utils import Pattern, _get_slicing_dim
import logging

log = logging.getLogger(__name__)

class BlockSplitter:
    """Can split a full DataSet object into blocks according to the given max slices
    per block. It provides an iterator interface, so that it can be used as::

         splitter = BlockSplitter(dataset, pattern, max_slices)
         for block in splitter:
             process_block(block)

    Where a block is a DataSet instance.

    Note that a slice of the data is returned and no copy is made.
    Also note that the dataset is copied to CPU if not there already.
    """

    def __init__(self, full_data: DataSet, pattern: Pattern, max_slices: int):
        self._full_data = full_data
        self._full_data.to_cpu()
        self._pattern = pattern
        self._slicing_dim = _get_slicing_dim(pattern) - 1
        self._max_slices = int(min(max_slices, full_data.data.shape[self._slicing_dim]))
        self._num_blocks = math.ceil(
            full_data.data.shape[self._slicing_dim] / self._max_slices
        )

    @property
    def slices_per_block(self) -> int:
        return self._max_slices

    def __len__(self):
        return self._num_blocks

    def __getitem__(self, idx: int) -> DataSet:
        assert self._slicing_dim in [
            0,
            1,
        ], "Only supporting slicing in projection and sinogram dimension"

        # dim, startidx, length -> DataSet
        return self._full_data.make_block(
            self._slicing_dim, idx * self.slices_per_block, self.slices_per_block
        )

    def __iter__(self) -> Iterator[DataSet]:
        class BlockIterator:
            def __init__(self, splitter):
                self.splitter = splitter
                self._current = 0

            def __next__(self) -> DataSet:
                if self._current >= len(self.splitter):
                    raise StopIteration
                v = self.splitter[self._current]
                self._current += 1
                return v

        return BlockIterator(self)


class BlockAggregator:
    """Aggregates multiple blocks back into the full dataset (after blockwise processing).

    Note that the dataset is copied to CPU if not there already
    """

    def __init__(self, full_dataset: DataSet, pattern: Pattern):
        self._dataset = full_dataset
        self._dataset.to_cpu()
        self._current_idx = 0
        self._slicing_dim = _get_slicing_dim(pattern) - 1
        self._full_size = full_dataset.data.shape[self._slicing_dim]
        log.debug(f"created aggregator: dim={self._slicing_dim}, full_size={self._full_size}")

    def append(self, dataset: DataSet):
        append_size = dataset.data.shape[self._slicing_dim]
        log.debug(f"appending {append_size}, current={self._current_idx}, full={self._full_size} (dim={self._slicing_dim})")
        if append_size + self._current_idx > self._full_size:
            raise ValueError(
                f"Cannot append another {append_size} slices - only {self._full_size-self._current_idx} slices left"
            )
        self._increase_dims_if_needed(dataset.data.shape, dataset.data.dtype)
        to_idx = [slice(None), slice(None), slice(None)]
        to_idx[self._slicing_dim] = slice(
            self._current_idx, self._current_idx + append_size
        )
        dataset.to_cpu()
        self._dataset.data[tuple(to_idx)] = dataset.data
        self._current_idx += append_size

    def _increase_dims_if_needed(self, append_data_shape: tuple, append_dtype: np.dtype):
        other_dims = np.delete(append_data_shape, self._slicing_dim)
        other_dims_full = np.delete(self._dataset.data.shape, self._slicing_dim)
        if any(other != this for other, this in zip(other_dims_full, other_dims)) or append_dtype != self._dataset.data.dtype:
            if self._current_idx != 0:
                raise ValueError(
                    f"Received block of shape {append_data_shape} and type {append_dtype},"
                    + f" while full data is of the different shape {self._dataset.data.shape} or type {self._dataset.data.dtype}"
                    + " and already has data blocks"
                )
            new_full_shape = np.insert(other_dims, self._slicing_dim, self._full_size)
            new_global_shape = np.insert(other_dims, self._slicing_dim, self._dataset.global_shape[self._slicing_dim])
            # need a new object, otherwise we might modify the source in-place
            self._dataset = DataSet(
                data=np.empty(new_full_shape, append_dtype),
                darks=self._dataset.darks,
                flats=self._dataset.flats,
                angles=self._dataset.angles,
                global_index=self._dataset.global_index,
                global_shape=tuple(new_global_shape)
            )

    @property
    def full_dataset(self) -> DataSet:
        if self._current_idx != self._full_size:
            raise ValueError(
                f"Aggregation not finished - {self._current_idx} slices of {self._full_size} have been aggregated"
            )

        return self._dataset
