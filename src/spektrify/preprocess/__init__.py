"""Preprocessing: registered, composable steps applied after loading.

>>> from spektrify.preprocess import Pipeline
>>> cube = Pipeline.parse(["calibrate:dark=dark.npy,white=white.npy", "bin:2"]).apply(cube)
"""

from spektrify.preprocess import corrections as _corrections  # noqa: F401  (register)
from spektrify.preprocess import spectral as _spectral  # noqa: F401
from spektrify.preprocess import steps as _steps  # noqa: F401
from spektrify.preprocess.base import (
    Pipeline,
    Step,
    make_step,
    param,
    register_step,
    step_schema,
)

__all__ = ["Pipeline", "Step", "make_step", "param", "register_step", "step_schema"]
