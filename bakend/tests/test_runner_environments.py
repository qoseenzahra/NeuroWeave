from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.execution.runners.freesurfer import FreeSurferReconAllRunner
from app.execution.runners.mrtrix_pipeline import MrtrixFiveTtGenRunner


class RunnerEnvironmentTests(unittest.TestCase):
    def test_freesurfer_environment_contains_delegated_tool_paths(self) -> None:
        home = Path("/opt/test/freesurfer")
        with patch.dict(
            os.environ,
            {
                "LOCALFLOW_FREESURFER_HOME": str(home),
                "LOCALFLOW_FSL_ROOT": "/opt/test/fsl",
                "PATH": "/usr/local/bin:/usr/bin:/bin",
            },
            clear=False,
        ):
            runner = FreeSurferReconAllRunner()
            environment = runner.execution_environment(Path("/outputs/subjects"))

        path_parts = environment["PATH"].split(os.pathsep)
        self.assertEqual(path_parts[0], str(home / "bin"))
        self.assertIn(str(home / "fsfast" / "bin"), path_parts)
        self.assertIn(str(home / "tktools"), path_parts)
        self.assertIn(str(home / "mni" / "bin"), path_parts)
        self.assertEqual(environment["MINC_BIN_DIR"], str(home / "mni" / "bin"))
        self.assertEqual(environment["MINC_LIB_DIR"], str(home / "mni" / "lib"))
        self.assertEqual(environment["MNI_DIR"], str(home / "mni"))
        self.assertEqual(environment["SUBJECTS_DIR"], str(Path("/outputs/subjects")))
        self.assertEqual(environment["FREESURFER"], str(home))

    def test_mrtrix_five_tt_environment_contains_mrtrix_and_fsl(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LOCALFLOW_MRTRIX_ROOT": "/opt/test/mrtrix",
                "LOCALFLOW_FSL_ROOT": "/opt/test/fsl",
                "PATH": "/usr/local/bin:/usr/bin:/bin",
            },
            clear=False,
        ):
            environment = MrtrixFiveTtGenRunner.execution_environment()

        path_parts = environment["PATH"].split(os.pathsep)
        self.assertEqual(path_parts[0], str(Path("/opt/test/fsl/bin")))
        self.assertEqual(path_parts[1], str(Path("/opt/test/mrtrix/bin")))
        self.assertEqual(environment["FSLDIR"], str(Path("/opt/test/fsl")))


if __name__ == "__main__":
    unittest.main()
