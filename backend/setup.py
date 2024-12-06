from setuptools import setup

setup(
    name="backend",
    author="Charles Baynham",
    version="0.1",
    package_dir={"backend": "."},
    install_requires=[],
    entry_points={
        "console_scripts": [
            "qr_gen = backend.generate_qr_items:generate",
        ],
    },
)
