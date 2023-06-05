import setuptools
from setuptools.command.build_py import build_py
import sys
import subprocess


class Build(build_py):
	"""Customized setuptools build command - builds protos on build."""
	def run(self):
		protoc_command = ["make", "-C","src/qubic/qasmqubic"]
		if subprocess.call(protoc_command) != 0:
			sys.exit(-1)
		build_py.run(self)

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="qubic",
    version="0.0.1",
    description="Quantum bit Control",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://gitlab.com/LBL-QubiC/software",
	#    project_urls={
	#    "Bug Tracker": "https://github.com/pypa/sampleproject/issues",
	#},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: LICENSE",
        "Operating System :: OS Independent",
    ],
    package_dir={"": "."},
    packages=setuptools.find_packages(where="qubic"),
    python_requires=">=3.6",
	cmdclass={
		"build_py": Build,
		},
	include_package_data=True,
	package_data={
		"": ["*.json"],
		},
	extra_requires={
		"antlr4-python3-runtime": ['antlr4-python3-runtime==4.7.2'],
		"numpy": ['numpy>1.20'],
		"scipy": ['scipy>1.7'],
		"scikit-learn": ['scipy>=0.0'],
		},
	install_requires=[
        "antlr4-python3-runtime==4.7.2",
		"numpy",
		"scipy",
		"scikit-learn"
		],
)
