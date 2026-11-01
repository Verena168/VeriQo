"""Curated technical-skill taxonomy.

Off-the-shelf NER models have no SKILL label, so skills are recognised with a spaCy
EntityRuler built from this list. Each entry: canonical name -> (category, aliases).
Aliases in CASE_SENSITIVE are only matched with their exact casing, because their
lowercase forms are ordinary English words ("go", "spring", "express", "r").
"""

CATEGORIES = {
    "language": "Programming Languages",
    "frontend": "Frontend",
    "backend": "Backend",
    "mobile": "Mobile",
    "database": "Databases",
    "ml": "Machine Learning & AI",
    "data": "Data Engineering & Analytics",
    "devops": "DevOps & Cloud",
    "security": "Security",
    "blockchain": "Blockchain",
    "design": "Design & Product",
    "iot": "IoT & Embedded",
    "tools": "Tools & Practices",
}

SKILLS: dict[str, tuple[str, list[str]]] = {
    # Languages
    "Python": ("language", ["python", "python3"]),
    "JavaScript": ("language", ["javascript", "js", "ecmascript", "es6"]),
    "TypeScript": ("language", ["typescript", "ts"]),
    "Java": ("language", ["java"]),
    "C": ("language", ["C", "ansi c"]),
    "C++": ("language", ["c++", "cpp"]),
    "C#": ("language", ["c#", "csharp"]),
    "Go": ("language", ["Go", "golang"]),
    "Rust": ("language", ["rust"]),
    "Kotlin": ("language", ["kotlin"]),
    "Swift": ("language", ["Swift"]),
    "Dart": ("language", ["Dart"]),
    "Ruby": ("language", ["ruby"]),
    "PHP": ("language", ["php"]),
    "R": ("language", ["R", "rstudio"]),
    "Scala": ("language", ["scala"]),
    "MATLAB": ("language", ["matlab"]),
    "SQL": ("language", ["sql", "t-sql", "pl/sql"]),
    "Bash": ("language", ["bash", "shell scripting", "shell script"]),
    "Solidity": ("blockchain", ["solidity"]),
    # Frontend
    "HTML": ("frontend", ["html", "html5"]),
    "CSS": ("frontend", ["css", "css3"]),
    "React": ("frontend", ["react", "react.js", "reactjs"]),
    "Next.js": ("frontend", ["next.js", "nextjs"]),
    "Vue.js": ("frontend", ["vue", "vue.js", "vuejs"]),
    "Angular": ("frontend", ["angular", "angularjs"]),
    "Svelte": ("frontend", ["svelte", "sveltekit"]),
    "Tailwind CSS": ("frontend", ["tailwind", "tailwindcss", "tailwind css"]),
    "Bootstrap": ("frontend", ["bootstrap"]),
    "Redux": ("frontend", ["redux"]),
    "Three.js": ("frontend", ["three.js", "threejs"]),
    # Backend
    "Node.js": ("backend", ["node.js", "nodejs", "node js"]),
    "Express.js": ("backend", ["express.js", "expressjs", "Express"]),
    "Django": ("backend", ["django"]),
    "Flask": ("backend", ["flask"]),
    "FastAPI": ("backend", ["fastapi"]),
    "Spring Boot": ("backend", ["spring boot", "springboot", "Spring"]),
    "ASP.NET": ("backend", ["asp.net", ".net", "dotnet", ".net core"]),
    "Ruby on Rails": ("backend", ["ruby on rails", "Rails"]),
    "Laravel": ("backend", ["laravel"]),
    "GraphQL": ("backend", ["graphql"]),
    "REST APIs": ("backend", ["rest api", "rest apis", "restful", "restful apis"]),
    "gRPC": ("backend", ["grpc"]),
    "WebSockets": ("backend", ["websocket", "websockets", "socket.io"]),
    "Microservices": ("backend", ["microservices", "microservice"]),
    # Mobile
    "Android": ("mobile", ["android", "android studio"]),
    "iOS": ("mobile", ["ios"]),
    "Flutter": ("mobile", ["flutter"]),
    "React Native": ("mobile", ["react native", "react-native"]),
    "Jetpack Compose": ("mobile", ["jetpack compose"]),
    "SwiftUI": ("mobile", ["swiftui"]),
    # Databases
    "PostgreSQL": ("database", ["postgresql", "postgres", "psql"]),
    "MySQL": ("database", ["mysql", "mariadb"]),
    "MongoDB": ("database", ["mongodb", "mongo", "mongoose"]),
    "SQLite": ("database", ["sqlite"]),
    "Redis": ("database", ["redis"]),
    "Firebase": ("database", ["firebase", "firestore"]),
    "Supabase": ("database", ["supabase"]),
    "Elasticsearch": ("database", ["elasticsearch", "elastic search"]),
    "Cassandra": ("database", ["cassandra"]),
    "Neo4j": ("database", ["neo4j"]),
    "DynamoDB": ("database", ["dynamodb"]),
    # ML / AI
    "Machine Learning": ("ml", ["machine learning", "ml"]),
    "Deep Learning": ("ml", ["deep learning", "dl", "neural networks", "neural network"]),
    "Natural Language Processing": ("ml", ["natural language processing", "nlp"]),
    "Computer Vision": ("ml", ["computer vision", "image processing"]),
    "Generative AI": ("ml", ["generative ai", "genai", "llm", "llms", "large language models", "prompt engineering"]),
    "TensorFlow": ("ml", ["tensorflow", "keras"]),
    "PyTorch": ("ml", ["pytorch", "torch"]),
    "scikit-learn": ("ml", ["scikit-learn", "sklearn", "scikit learn"]),
    "Hugging Face": ("ml", ["hugging face", "huggingface", "transformers"]),
    "OpenCV": ("ml", ["opencv", "cv2"]),
    "LangChain": ("ml", ["langchain"]),
    "Reinforcement Learning": ("ml", ["reinforcement learning"]),
    "XGBoost": ("ml", ["xgboost", "lightgbm"]),
    # Data
    "Pandas": ("data", ["pandas"]),
    "NumPy": ("data", ["numpy"]),
    "Data Analysis": ("data", ["data analysis", "data analytics", "exploratory data analysis", "eda"]),
    "Data Visualization": ("data", ["data visualization", "matplotlib", "seaborn", "plotly", "d3.js", "d3"]),
    "Power BI": ("data", ["power bi", "powerbi"]),
    "Tableau": ("data", ["tableau"]),
    "Apache Spark": ("data", ["spark", "pyspark", "apache spark"]),
    "Apache Kafka": ("data", ["kafka", "apache kafka"]),
    "Airflow": ("data", ["airflow", "apache airflow"]),
    "ETL": ("data", ["etl", "data pipelines", "data pipeline"]),
    # DevOps / Cloud
    "Docker": ("devops", ["docker", "dockerfile", "docker compose", "docker-compose"]),
    "Kubernetes": ("devops", ["kubernetes", "k8s"]),
    "AWS": ("devops", ["aws", "amazon web services", "ec2", "aws lambda"]),
    "Google Cloud": ("devops", ["gcp", "google cloud", "google cloud platform"]),
    "Azure": ("devops", ["azure", "microsoft azure"]),
    "CI/CD": ("devops", ["ci/cd", "github actions", "jenkins", "gitlab ci", "continuous integration"]),
    "Terraform": ("devops", ["terraform"]),
    "Linux": ("devops", ["linux", "ubuntu", "unix"]),
    "Nginx": ("devops", ["nginx"]),
    "Vercel": ("devops", ["vercel", "netlify"]),
    # Security
    "Cybersecurity": ("security", ["cybersecurity", "cyber security", "information security", "infosec"]),
    "Penetration Testing": ("security", ["penetration testing", "pentesting", "ethical hacking", "burp suite"]),
    "Cryptography": ("security", ["cryptography"]),
    "OAuth": ("security", ["oauth", "oauth2", "jwt"]),
    # Blockchain
    "Blockchain": ("blockchain", ["blockchain", "web3", "smart contracts", "smart contract"]),
    "Ethereum": ("blockchain", ["ethereum", "evm", "hardhat", "truffle"]),
    # Design / product
    "UI/UX Design": ("design", ["ui/ux", "ux design", "ui design", "user experience", "user interface design"]),
    "Figma": ("design", ["figma"]),
    "Product Management": ("design", ["product management", "product manager"]),
    # IoT / embedded
    "Arduino": ("iot", ["arduino"]),
    "Raspberry Pi": ("iot", ["raspberry pi"]),
    "IoT": ("iot", ["iot", "internet of things"]),
    "Embedded Systems": ("iot", ["embedded systems", "embedded c", "microcontrollers", "esp32"]),
    # Tools / practices
    "Git": ("tools", ["git", "github", "gitlab", "version control"]),
    "Unit Testing": ("tools", ["unit testing", "pytest", "jest", "junit", "test-driven development", "tdd"]),
    "Agile": ("tools", ["agile", "scrum", "kanban"]),
    "System Design": ("tools", ["system design", "distributed systems"]),
    "Data Structures & Algorithms": ("tools", ["data structures", "algorithms", "dsa", "competitive programming"]),
}

# GitHub's repo.language values -> canonical skill names (only where they differ).
GITHUB_LANGUAGE_MAP = {
    "Jupyter Notebook": "Python",
    "Shell": "Bash",
    "PowerShell": "Bash",
    "Vue": "Vue.js",
    "HTML": "HTML",
    "CSS": "CSS",
    "SCSS": "CSS",
    "C#": "C#",
    "Objective-C": "iOS",
    "PLpgSQL": "SQL",
    "TSQL": "SQL",
    "HCL": "Terraform",
    "Dockerfile": "Docker",
}

CASE_SENSITIVE = {"C", "Go", "R", "Swift", "Dart", "Spring", "Express", "Rails"}


def category_of(skill: str) -> str | None:
    entry = SKILLS.get(skill)
    return entry[0] if entry else None


_ALIAS_INDEX: dict[str, str] = {}
for _canon, (_cat, _aliases) in SKILLS.items():
    _ALIAS_INDEX[_canon.lower()] = _canon
    for _a in _aliases:
        if _a not in CASE_SENSITIVE:
            _ALIAS_INDEX[_a.lower()] = _canon


def canonicalize(name: str) -> str | None:
    """Map free text such as "reactjs" or a GitHub language to a canonical skill, if known."""
    name = name.strip()
    if name in GITHUB_LANGUAGE_MAP:
        return GITHUB_LANGUAGE_MAP[name]
    if name in SKILLS:
        return name
    return _ALIAS_INDEX.get(name.lower())
