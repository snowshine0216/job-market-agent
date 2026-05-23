def test_python_runtime_is_3_12_plus() -> None:
    import sys

    assert sys.version_info >= (3, 12)


def test_jma_package_is_importable() -> None:
    import jma

    assert jma.__doc__ is not None
