"""
Some unit tests for the yaml checker
"""
import pytest
import yaml

from httomo.yaml_checker import (
    check_all_stages_defined,
    check_all_stages_non_empty,
    check_first_stage_has_loader,
    check_loading_stage_one_method,
    check_one_method_per_module,
    sanity_check,
    validate_yaml_config,
)
from httomo.yaml_loader import YamlLoader


def test_sanity_check(sample_pipelines, yaml_loader: type[YamlLoader]):
    wrong_indentation_pipeline = (
        sample_pipelines + "testing/wrong_indentation_pipeline.yaml"
    )
    with open(wrong_indentation_pipeline, "r") as f:
        conf_generator = yaml.load_all(f, Loader=yaml_loader)
        # `assert` needs to be in `with` block for this case, because
        # `conf_generator` is lazy-loaded from the file when converted to a
        # list inside `sanity_check()`
        assert not sanity_check(conf_generator)


def test_missing_loader_stage(sample_pipelines, yaml_loader: type[YamlLoader]):
    missing_loader_stage_pipeline = (
        sample_pipelines + "testing/missing_loader_stage.yaml"
    )
    with open(missing_loader_stage_pipeline, "r") as f:
        conf = list(yaml.load_all(f, Loader=yaml_loader))
    assert not check_all_stages_defined(conf)


def test_empty_loader_stage(sample_pipelines, yaml_loader: type[YamlLoader]):
    empty_loader_stage_pipeline = (
        sample_pipelines + "testing/empty_loader_stage.yaml"
    )
    with open(empty_loader_stage_pipeline, "r") as f:
        conf = list(yaml.load_all(f, Loader=yaml_loader))
    assert not check_all_stages_non_empty(conf)


def test_invalid_loader_stage(sample_pipelines, yaml_loader: type[YamlLoader]):
    invalid_loader_stage_pipeline = (
        sample_pipelines + "testing/invalid_loader_stage.yaml"
    )
    with open(invalid_loader_stage_pipeline, "r") as f:
        conf = list(yaml.load_all(f, Loader=yaml_loader))
    assert not check_loading_stage_one_method(conf)


def test_first_stage_has_loader(sample_pipelines, yaml_loader: type[YamlLoader]):
    incorrect_first_stage_pipeline = (
        sample_pipelines + "testing/incorrect_first_stage.yaml"
    )
    with open(incorrect_first_stage_pipeline, "r") as f:
        conf = list(yaml.load_all(f, Loader=yaml_loader))
    assert not check_first_stage_has_loader(conf)


def test_one_method_per_module(more_than_one_method, yaml_loader: type[YamlLoader]):
    with open(more_than_one_method, "r") as f:
        conf = list(yaml.load_all(f, Loader=yaml_loader))
    assert not check_one_method_per_module(conf)


@pytest.mark.parametrize(
    "yaml_file, expected",
    [
        ("testing/incorrect_method.yaml", False),
        ("02_basic_cpu_pipeline_tomo_standard.yaml", True),
        ("03_basic_gpu_pipeline_tomo_standard.yaml", True),
        ("parameter_sweeps/02_median_filter_kernel_sweep.yaml", True),
        ("testing/incorrect_path.yaml", False),
        ("testing/required_param.yaml", False),
    ],
    ids=[
        "incorrect_method",
        "cpu_pipeline",
        "gpu_pipeline",
        "sweep_pipeline",
        "incorrect_path",
        "required_param",
    ],
)
def test_validate_yaml_config(sample_pipelines, yaml_file, standard_data, expected):
    yaml_file = sample_pipelines + yaml_file
    assert validate_yaml_config(yaml_file, standard_data) == expected
