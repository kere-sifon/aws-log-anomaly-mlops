"""Setuptools metadata for SageMaker /opt/ml/code (the container runs ``pip install .`` there)."""

from setuptools import setup

setup(
    name="log-anomaly-inference",
    version="1.0.0",
    py_modules=["inference"],
)
