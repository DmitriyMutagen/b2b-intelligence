# Выполнение кода в песочнице (Sandbox)

## Обзор

Модуль песочницы обеспечивает безопасные, настраиваемые среды выполнения кода для агента Antigravity. Он позволяет агенту запускать сгенерированный Python-код с различными уровнями изоляции и контроля ресурсов.

**Ключевой принцип:** Zero-Config по умолчанию (локальное выполнение), с опциональным Docker для более сильной изоляции.

## Быстрый старт

### Локальное выполнение (По умолчанию)

Настройка не требуется. Код запускается в изолированном подпроцессе на вашей машине:

```bash
python src/agent.py "Write and execute Python code to calculate 2 + 2"
```

Агент:
- Сгенерирует Python-код
- Выполнит его безопасно в изолированном подпроцессе
- Вернет результат

### Выполнение в Docker (Опционально)

Для более сильной изоляции (файловая система, сеть, ресурсы):

```bash
export SANDBOX_TYPE=docker
export DOCKER_IMAGE=antigravity-sandbox:latest

# Сначала соберите образ песочницы (опционально; использует python:3.11-slim по умолчанию)
docker build -f Dockerfile.sandbox -t antigravity-sandbox:latest .

# Затем запустите агента
python src/agent.py "Your code generation task"
```

## Конфигурация

Все поведение песочницы управляется через переменные окружения.

### Основные переменные

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `SANDBOX_TYPE` | `local` | Среда выполнения: `local`, `docker`, или `e2b` (в будущем) |
| `SANDBOX_TIMEOUT_SEC` | `30` | Максимальное время выполнения кода (секунды) |
| `SANDBOX_MAX_OUTPUT_KB` | `10` | Максимальный размер stdout/stderr до обрезания (KB) |

### Переменные для локального режима

Локальная песочница использует интерпретатор Python вашей системы внутри временной рабочей директории.

- Дополнительные переменные не требуются
- Работает сразу после `pip install -r requirements.txt`

### Переменные для Docker

Используются только когда `SANDBOX_TYPE=docker`.

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DOCKER_IMAGE` | `python:3.11-slim` | Базовый Docker-образ для использования |
| `DOCKER_NETWORK_ENABLED` | `false` | Разрешить сетевой доступ контейнеру |
| `DOCKER_CPU_LIMIT` | `0.5` | Лимит CPU (ядра) |
| `DOCKER_MEMORY_LIMIT` | `256m` | Лимит памяти |

### Примеры конфигурационных файлов

#### Локально (По умолчанию)

```bash
# .env или shell export
SANDBOX_TYPE=local
SANDBOX_TIMEOUT_SEC=30
SANDBOX_MAX_OUTPUT_KB=10
```

#### Docker (Изолированно)

```bash
SANDBOX_TYPE=docker
DOCKER_IMAGE=antigravity-sandbox:latest
DOCKER_NETWORK_ENABLED=false
DOCKER_CPU_LIMIT=0.5
DOCKER_MEMORY_LIMIT=256m
SANDBOX_TIMEOUT_SEC=60
SANDBOX_MAX_OUTPUT_KB=100
```

## Модель безопасности

### Локальная песочница

**Уровень изоляции:** Уровень процесса (подпроцесс)

**Предназначение:**
- Разработка и локальное тестирование
- Доверенный код от LLM в контролируемых средах
- Быстрая итерация с быстрым выполнением

**Свойства безопасности:**
- Код выполняется с тем же пользователем и правами, что и агент
- Нет изоляции файловой системы (запускается во временной директории, но доступен пользователю)
- Сетевой доступ доступен (если не отфильтрован в другом месте)
- Лимиты ресурсов: принудительный таймаут, размер вывода

**От чего защищает:**
- Зависшие процессы (принудительный таймаут)
- Исчерпание ресурсов (обрезание вывода)
- Загрязнение рабочей директории (изоляция временной директории)

**От чего НЕ защищает:**
- Вредоносный код, сгенерированный LLM, с доступом к ОС (например, `rm -rf`, сетевые атаки)
- **Рекомендация:** Используйте режим Docker для ненадежных источников кода

### Песочница Docker

**Уровень изоляции:** Уровень контейнера (Linux namespaces, cgroups)

**Предназначение:**
- Продакшен среды
- Ненадежный или полу-надежный код
- Многопользовательские системы

**Свойства безопасности:**
- Изоляция файловой системы (контейнер имеет независимую rootfs)
- Сетевая изоляция (`--network=none` по умолчанию)
- Сброс capabilities (минимальные привилегии)
- Лимиты ресурсов (CPU, память)
- Убийство процесса по таймауту

**От чего защищает:**
- Доступ к файловой системе за пределами монтирования `/work` (только для чтения в большинстве случаев)
- Сетевые атаки (сеть отключена)
- Исчерпание ресурсов (лимиты CPU/памяти)
- Риск эскалации привилегий (дополнительно снижен при использовании защищенного non-root образа, такого как `Dockerfile.sandbox`)

**От чего НЕ защищает:**
- Побег из контейнера (возможно, но редко; зависит от версии ядра и версии Docker)
- **Рекомендация:** Держите Docker и ядро обновленными; относитесь как к "защите в глубину", а не абсолютной изоляции

### Будущее: Облачная песочница (E2B)

**Ожидается в Фазе 9C** — Полная мультитенантная изоляция через удаленные VM или Firecracker microVM.

## Использование песочницы в коде

### Прямой API

```python
from src.sandbox.factory import get_sandbox

sandbox = get_sandbox()  # Возвращает настроенную песочницу (local или docker)

result = sandbox.execute(
    code="print('Hello')",
    language="python",
    timeout=30
)

print(f"Код выхода: {result.exit_code}")
print(f"Вывод: {result.stdout}")
print(f"Длительность: {result.duration:.2f}s")
print(f"Метаданные: {result.meta}")
```

### Через инструмент агента

Агент может получить доступ к песочнице через инструмент `run_python_code`:

```python
from src.tools.execution_tool import run_python_code

result = run_python_code(
    code="print('Executed by agent')",
    timeout=30
)
print(result)  # Компактный строковый вывод или сообщение об ошибке
```

## Сборка пользовательских образов песочницы

Если `DOCKER_IMAGE` указывает на пользовательский образ, вы можете собрать его с помощью:

```bash
docker build -f Dockerfile.sandbox -t my-sandbox:latest .
```

Включенный `Dockerfile.sandbox` предоставляет:
- `python:3.11-slim` база
- Общие пакеты: `numpy`, `pandas`, `requests`, `matplotlib`, `scipy`
- Non-root пользователь `sandbox` для безопасности
- `/work` как директория выполнения

### Настройка под ваши нужды

```dockerfile
# Dockerfile.sandbox.custom
FROM python:3.11-slim

# Добавьте ваши пакеты
RUN pip install --no-cache-dir \
    tensorflow \
    torch \
    scikit-learn

# ... остальная часть оригинального Dockerfile.sandbox
```

Затем:

```bash
export DOCKER_IMAGE=my-sandbox:latest
docker build -f Dockerfile.sandbox.custom -t my-sandbox:latest .
python src/agent.py "Your task"
```

## Устранение неполадок

### "Docker daemon not available"

**Проблема:** Вы установили `SANDBOX_TYPE=docker`, но Docker не запущен.

**Решение:**
```bash
# Запустите Docker демон
sudo systemctl start docker  # Linux
# или используйте Docker Desktop (macOS/Windows)

# Проверьте
docker ps
```

### "Docker permission denied"

**Проблема:** Ваш пользователь не в группе `docker`.

**Решение:**
```bash
# Добавьте пользователя в группу docker (требуется sudo)
sudo usermod -aG docker $USER

# Активируйте группу (или перелогиньтесь)
newgrp docker

# Тест
docker ps
```

### Таймаут в локальной песочнице

**Проблема:** Код выполняется дольше, чем `SANDBOX_TIMEOUT_SEC`.

**Решение:**
```bash
# Увеличьте таймаут
export SANDBOX_TIMEOUT_SEC=120

# Или сделайте код более эффективным
```

### Вывод обрезан

**Проблема:** Вывод выполнения превышает `SANDBOX_MAX_OUTPUT_KB`.

**Решение:**
```bash
# Увеличьте лимит
export SANDBOX_MAX_OUTPUT_KB=100

# Или уменьшите логирование в генерируемом коде
```

## Производительность

### Типичные задержки

| Режим | Первый запуск | Теплый запуск | Таймаут (5s) |
|-------|---------------|---------------|--------------|
| Local | <50ms | <50ms | <5.1s |
| Docker | 1-3s | <100ms | <5.1s |

Первый запуск Docker медленнее из-за загрузки образа и старта контейнера. Последующие запуски используют кэшированные слои.

## Примеры

### Пример 1: Простые вычисления

```bash
python src/agent.py "Calculate the sum of numbers 1 to 100"
```

Агент генерирует и выполняет:
```python
print(sum(range(1, 101)))
```

Вывод локальной песочницы: `5050` (мгновенно)

### Пример 2: Анализ данных

```bash
export SANDBOX_TYPE=docker
python src/agent.py "Analyze a sample CSV and show mean of values"
```

Агент генерирует и выполняет в Docker:
```python
import pandas as pd
data = pd.read_csv("data.csv")
print(data.mean())
```

Вывод: Форматированная статистика

### Пример 3: Длительная задача

```bash
export SANDBOX_TIMEOUT_SEC=300
python src/agent.py "Train a simple model on sample data"
```

Таймаут установлен на 5 минут для обучения.

## Тестирование

Запустите набор тестов песочницы:

```bash
pytest tests/test_local_sandbox.py tests/test_docker_sandbox.py tests/test_factory.py -v
```

- **Локальные тесты** всегда запускаются
- **Docker тесты** пропускаются автоматически, если демон недоступен
- Все тесты проверяют контракты данных и пути ошибок

## Вклад в проект (Contributing)

Чтобы добавить новый тип песочницы (например, Kubernetes, E2B):

1. Создайте `src/sandbox/your_runtime.py` с классом `YourSandbox`
2. Реализуйте протокол `CodeSandbox` (см. `base.py`)
3. Обновите `factory.py`, чтобы распознавать ваш тип через переменную env
4. Добавьте тесты в `tests/test_your_runtime.py`
5. Обновите эту документацию

См. `src/sandbox/docker_exec.py` для полного примера.

## Ссылки

- [Спецификация выполнения кода в песочнице](../../openspec/changes/2026-01-09-add-sandbox-execution/specs/sandbox/spec.md)
- [Предложение OpenSpec](../../openspec/changes/2026-01-09-add-sandbox-execution/proposal.md)
- [Дорожная карта Фаза 9A](../ROADMAP.md#phase-9a-sandbox-environment-)
