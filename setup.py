from setuptools import find_packages, setup


setup(
    name="rpp-orchestrator",
    version="0.1.0",
    description="RPP orchestration and workspace management",
    packages=find_packages(include=["rpp_orchestrator", "rpp_orchestrator.*"]),
    package_dir={"": "."},
    include_package_data=True,
    install_requires=["PyQt6"],
    entry_points={
        "console_scripts": [
            "rpp-orchestrator=rpp_orchestrator.cli:main",
        ]
    },
)
