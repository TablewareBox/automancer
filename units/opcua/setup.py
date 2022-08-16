from setuptools import find_packages, setup

setup(
  name="pr1_opcua",
  version="0.0.0",

  packages=find_packages(where="src"),
  package_dir={"": "src"},

  entry_points={
    'pr1.units': [
      "opcua = pr1_opcua",
    ]
  },
  package_data={
    "pr1_opcua.pr1_opcua.client": ["*.js"]
  },

  install_requires=[
    # "opcua==0.98.13",
    "asyncua==0.9.94"
  ]
)
