import numpy as np
import pytest
from httomo.runner.block_split import BlockAggregator, BlockSplitter
from httomo.runner.dataset import DataSet
from httomo.utils import Pattern, gpu_enabled, xp


def test_block_splitter_gives_full_when_fits(dummy_dataset: DataSet):
    splitter = BlockSplitter(dummy_dataset, Pattern.projection, 100000000)

    assert splitter.slices_per_block == dummy_dataset.data.shape[0]
    assert len(splitter) == 1


def test_block_splitter_splits_evenly(dummy_dataset: DataSet):
    assert (
        dummy_dataset.data.shape[0] % 2 == 0
    ), "explicitly make sure dummy data is even"

    splitter = BlockSplitter(
        dummy_dataset, Pattern.projection, dummy_dataset.data.shape[0] // 2
    )

    assert splitter.slices_per_block == dummy_dataset.data.shape[0] // 2
    assert len(splitter) == 2


def test_block_splitter_splits_odd(dummy_dataset: DataSet):
    assert (
        dummy_dataset.data.shape[0] % 3 != 0
    ), "explicitly make sure dummy data is not"

    splitter = BlockSplitter(
        dummy_dataset, Pattern.projection, dummy_dataset.data.shape[0] // 3
    )

    assert splitter.slices_per_block == dummy_dataset.data.shape[0] // 3
    assert len(splitter) == 4


def test_block_gives_dataset_full(dummy_dataset: DataSet):
    splitter = BlockSplitter(dummy_dataset, Pattern.projection, 100000000)
    assert splitter[0].data.shape == dummy_dataset.data.shape


def test_block_gives_blocks_projection(dummy_dataset: DataSet):
    dummy_dataset.data = np.random.random(dummy_dataset.data.shape).astype(np.float32)

    max_slices = dummy_dataset.data.shape[0] // 2
    splitter = BlockSplitter(dummy_dataset, Pattern.projection, max_slices)

    np.testing.assert_array_equal(
        splitter[0].data, dummy_dataset.data[0:max_slices, :, :]
    )
    np.testing.assert_array_equal(
        splitter[1].data, dummy_dataset.data[max_slices:, :, :]
    )


def test_block_gives_blocks_sino(dummy_dataset: DataSet):
    dummy_dataset.data = np.random.random(dummy_dataset.data.shape).astype(np.float32)

    max_slices = dummy_dataset.data.shape[1] // 2
    splitter = BlockSplitter(dummy_dataset, Pattern.sinogram, max_slices)

    np.testing.assert_array_equal(
        splitter[0].data, dummy_dataset.data[:, 0:max_slices, :]
    )
    np.testing.assert_array_equal(
        splitter[1].data, dummy_dataset.data[:, max_slices:, :]
    )


def test_block_gives_blocks_odd(dummy_dataset: DataSet):
    dummy_dataset.data = np.random.random(dummy_dataset.data.shape).astype(np.float32)

    max_slices = dummy_dataset.data.shape[0] // 3
    splitter = BlockSplitter(dummy_dataset, Pattern.projection, max_slices)

    np.testing.assert_array_equal(
        splitter[0].data, dummy_dataset.data[0:max_slices, :, :]
    )
    np.testing.assert_array_equal(
        splitter[1].data, dummy_dataset.data[max_slices : 2 * max_slices, :, :]
    )
    np.testing.assert_array_equal(
        splitter[2].data, dummy_dataset.data[2 * max_slices : 3 * max_slices, :, :]
    )
    np.testing.assert_array_equal(
        splitter[3].data, dummy_dataset.data[3 * max_slices :, :, :]
    )


def test_block_can_iterate(dummy_dataset: DataSet):
    dummy_dataset.data = np.random.random(dummy_dataset.data.shape).astype(np.float32)

    max_slices = dummy_dataset.data.shape[1] // 2
    splitter = BlockSplitter(dummy_dataset, Pattern.projection, max_slices)

    for i, block in enumerate(splitter):
        np.testing.assert_array_equal(
            block.data, dummy_dataset.data[i * max_slices : (i + 1) * max_slices, :, :]
        )


def test_aggregator_throws_if_unfinished(dummy_dataset: DataSet):
    aggregator = BlockAggregator(dummy_dataset, Pattern.projection)
    with pytest.raises(ValueError) as e:
        aggregator.full_dataset

    assert "not finished" in str(e)


def test_aggregator_throws_if_partially_finished(dummy_dataset: DataSet):
    splitter = BlockSplitter(
        dummy_dataset, Pattern.projection, dummy_dataset.data.shape[0] // 2
    )
    aggregator = BlockAggregator(dummy_dataset, Pattern.projection)
    aggregator.append(splitter[0])

    with pytest.raises(ValueError) as e:
        aggregator.full_dataset

    assert "not finished" in str(e)


def test_aggregator_throws_if_aggregate_too_much(dummy_dataset: DataSet):
    aggregator = BlockAggregator(dummy_dataset, Pattern.projection)
    aggregator.append(dummy_dataset)

    with pytest.raises(ValueError) as e:
        aggregator.append(dummy_dataset)

    assert "only 0 slices left" in str(e)


@pytest.mark.parametrize("max_slices", [1, 3, 5, 100000])
def test_can_aggregate_full(dummy_dataset: DataSet, max_slices: int):
    splitter = BlockSplitter(dummy_dataset, Pattern.projection, max_slices)
    aggregator = BlockAggregator(dummy_dataset, Pattern.projection)

    for block in splitter:
        aggregator.append(block)

    res = aggregator.full_dataset

    np.testing.assert_array_equal(res.data, dummy_dataset.data)
    np.testing.assert_array_equal(res.darks, dummy_dataset.darks)
    np.testing.assert_array_equal(res.flats, dummy_dataset.flats)
    np.testing.assert_array_equal(res.angles, dummy_dataset.angles)


def test_can_aggregate_changed_dimensions(dummy_dataset: DataSet):
    splitter = BlockSplitter(
        dummy_dataset, Pattern.projection, dummy_dataset.data.shape[0] // 2
    )
    aggregator = BlockAggregator(dummy_dataset, Pattern.projection)

    for block in splitter:
        shape = list(block.data.shape)
        shape[1] += 3
        shape[2] += 5
        block.data = 2.0 * np.ones(tuple(shape), dtype=block.data.dtype)
        aggregator.append(block)

    res = aggregator.full_dataset

    expected_shape = list(dummy_dataset.data.shape)
    expected_shape[1] += 3
    expected_shape[2] += 5
    assert res.data.shape == tuple(expected_shape)
    np.testing.assert_array_equal(res.data, 2.0)


def test_changing_dimensions_in_second_block_fails(dummy_dataset: DataSet):
    splitter = BlockSplitter(
        dummy_dataset, Pattern.projection, dummy_dataset.data.shape[0] // 2
    )
    aggregator = BlockAggregator(dummy_dataset, Pattern.projection)
    aggregator.append(splitter[0])

    d = splitter[1]
    shape = list(d.data.shape)
    shape[1] += 3
    shape[2] += 5
    d.data = 2.0 * np.ones(tuple(shape), dtype=d.data.dtype)
    with pytest.raises(ValueError) as e:
        aggregator.append(d)

    assert "different shape" in str(e)


def test_can_aggregate_changed_datatype(dummy_dataset: DataSet):
    dummy_dataset.data = dummy_dataset.data.astype(np.uint16)
    splitter = BlockSplitter(
        dummy_dataset, Pattern.projection, dummy_dataset.data.shape[0] // 2
    )
    aggregator = BlockAggregator(dummy_dataset, Pattern.projection)

    for block in splitter:
        block.data = block.data.astype(np.float32)
        aggregator.append(block)

    res = aggregator.full_dataset

    assert res.data.dtype == np.float32
    # this works because data is all '1' values, so cast doesn't change value
    np.testing.assert_array_equal(res.data, dummy_dataset.data)


@pytest.mark.skipif(
    not gpu_enabled or xp.cuda.runtime.getDeviceCount() == 0,
    reason="skipped as cupy is not available",
)
@pytest.mark.cupy
def test_splitter_moves_to_cpu_if_not_already(dummy_dataset: DataSet):
    dummy_dataset.to_gpu()
    assert dummy_dataset.is_gpu
    _ = BlockSplitter(dummy_dataset, Pattern.projection, dummy_dataset.data.shape[0])

    assert dummy_dataset.is_cpu


@pytest.mark.skipif(
    not gpu_enabled or xp.cuda.runtime.getDeviceCount() == 0,
    reason="skipped as cupy is not available",
)
@pytest.mark.cupy
def test_aggregator_moves_to_cpu_if_not_already(dummy_dataset: DataSet):
    dummy_dataset.to_gpu()
    assert dummy_dataset.is_gpu
    _ = BlockAggregator(dummy_dataset, Pattern.projection)

    assert dummy_dataset.is_cpu


@pytest.mark.parametrize("max_slices", [1, 3, 5, 100000])
def test_preserves_global_slice_info(dummy_dataset: DataSet, max_slices: int):
    dummy_dataset = DataSet(
        data=dummy_dataset.data,
        flats=dummy_dataset.flats,
        darks=dummy_dataset.darks,
        angles=dummy_dataset.angles,
        global_index=(10, 0, 0),  # 10 slices from global start
        global_shape=(  # global shape is 20 more slices than local
            20 + dummy_dataset.shape[0],
            dummy_dataset.shape[1],
            dummy_dataset.shape[2],
        ),
    )
    splitter = BlockSplitter(dummy_dataset, Pattern.projection, max_slices)
    aggregator = BlockAggregator(dummy_dataset, Pattern.projection)

    count = 10
    for block in splitter:
        assert block.shape[1:] == dummy_dataset.shape[1:]
        assert block.shape[0] <= dummy_dataset.shape[0]
        assert block.shape[0] <= max_slices
        assert block.global_index == (count, 0, 0)
        assert block.global_shape == dummy_dataset.global_shape
        aggregator.append(block)
        count += block.shape[0]

    res = aggregator.full_dataset

    assert res.global_shape == dummy_dataset.global_shape
    assert res.global_index == (10, 0, 0)


def test_preserves_global_slice_info_changed_dims(dummy_dataset: DataSet):
    dummy_dataset = DataSet(
        data=dummy_dataset.data,
        flats=dummy_dataset.flats,
        darks=dummy_dataset.darks,
        angles=dummy_dataset.angles,
        global_index=(10, 0, 0),  # 10 slices from global start
        global_shape=(  # global shape is 20 more slices than local
            20 + dummy_dataset.shape[0],
            dummy_dataset.shape[1],
            dummy_dataset.shape[2],
        ),
    )

    splitter = BlockSplitter(
        dummy_dataset, Pattern.projection, dummy_dataset.data.shape[0] // 2
    )
    aggregator = BlockAggregator(dummy_dataset, Pattern.projection)

    for block in splitter:
        shape = list(block.data.shape)
        shape[1] += 3
        shape[2] += 5
        block.data = 2.0 * np.ones(tuple(shape), dtype=block.data.dtype)
        aggregator.append(block)

    res = aggregator.full_dataset

    assert res.global_shape == (dummy_dataset.global_shape[0], dummy_dataset.global_shape[1] + 3, dummy_dataset.global_shape[2] + 5)
    assert res.global_index == (10, 0, 0)
    