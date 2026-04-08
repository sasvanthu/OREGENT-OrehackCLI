import os
import json


TECH_SIGNATURES = {
    "ml": [
        "torch", "tensorflow", "sklearn", "scikit-learn",
        "xgboost", "lightgbm", "keras", "transformers", "huggingface"
    ],
    "computer_vision": [
        "cv2", "opencv", "mediapipe", "pillow", "pil",
        "imageio", "skimage", "scikit-image"
    ],
    "web_backend": [
        "flask", "fastapi", "django", "express", "spring",
        "gin", "fiber", "rails", "laravel", "nestjs", "koa"
    ],
    "frontend": [
        "react", "vue", "angular", "next", "nuxt",
        "svelte", "gatsby", "vite"
    ],
    "mobile": [
        "flutter", "react-native", "expo", "ionic"
    ],
    "desktop": [
        "pyqt", "tkinter", "wxpython", "kivy", "electron"
    ],
    "data": [
        "pandas", "numpy", "polars", "dask", "pyspark"
    ],
    "database": [
        "sqlalchemy", "pymongo", "psycopg2", "redis",
        "motor", "peewee", "tortoise"
    ],
    "api": [
        "requests", "httpx", "axios", "aiohttp", "urllib"
    ],
    "devops": [
        "docker", "kubernetes", "ansible", "terraform"
    ],
    "security": [
        "bandit", "safety", "cryptography", "jwt",
        "owasp", "nmap", "scapy"
    ],
    "blockchain": [
        "web3", "solidity", "ethers", "hardhat", "truffle"
    ],
}


def detect_from_dependencies(dependencies):

    detected = {}

    dep_lower = [d.lower() for d in dependencies]

    for category, libs in TECH_SIGNATURES.items():
        matched = []
        for lib in libs:
            if any(lib in dep for dep in dep_lower):
                matched.append(lib)
        if matched:
            detected[category] = matched

    return detected


def detect_from_package_json(repo_path):

    path = os.path.join(repo_path, "package.json")
    detected = {}

    if not os.path.exists(path):
        return detected

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        dep_keys = list(deps.keys())

        for category, libs in TECH_SIGNATURES.items():
            matched = [lib for lib in libs if any(lib in k.lower() for k in dep_keys)]
            if matched:
                if category not in detected:
                    detected[category] = matched
                else:
                    detected[category].extend(matched)

    except Exception:
        pass

    return detected


def detect_from_repo_structure(repo_path, classified):

    detected = {}

    # Flutter
    if os.path.exists(os.path.join(repo_path, "pubspec.yaml")):
        detected["mobile"] = ["flutter"]

    # Spring / Maven
    if os.path.exists(os.path.join(repo_path, "pom.xml")):
        detected.setdefault("web_backend", []).append("spring")

    # Gradle (Android / Spring)
    if os.path.exists(os.path.join(repo_path, "build.gradle")):
        detected.setdefault("mobile", []).append("android")

    # Docker
    if os.path.exists(os.path.join(repo_path, "Dockerfile")):
        detected.setdefault("devops", []).append("docker")

    # Has frontend files
    if classified.get("frontend"):
        detected.setdefault("frontend", []).append("html/css")

    # Has SQL files
    for f in classified.get("dataset", []):
        if f.endswith(".sql"):
            detected.setdefault("database", []).append("sql")
            break

    return detected


def detect_tech_stack(repo_path, code_metrics, classified):
    """
    Returns a structured dict of detected tech categories and
    the specific libraries/tools found under each.
    """

    dependencies = code_metrics.get("dependencies", [])

    from_deps = detect_from_dependencies(dependencies)
    from_pkg = detect_from_package_json(repo_path)
    from_struct = detect_from_repo_structure(repo_path, classified)

    # Merge all three
    merged = {}

    for source in [from_deps, from_pkg, from_struct]:
        for category, libs in source.items():
            if category not in merged:
                merged[category] = list(set(libs))
            else:
                merged[category] = list(set(merged[category] + libs))

    return merged
