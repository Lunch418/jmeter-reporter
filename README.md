# 📊 Инструкция по генерации отчетов JMeter

## Описание
Этот скрипт автоматически преобразует результаты нагрузочного тестирования JMeter из Jenkins в красиво оформленный Excel отчет с графиками и таблицами.

---

## 📋 Что вам понадобится

### 1. Python 3.6+
Убедитесь, что Python установлен:
```bash
python3 --version
```

### 2. Библиотека openpyxl
Установите зависимость:
```bash
pip install openpyxl
```

### 3. Три файла из Jenkins
Нужно скачать из артефактов тестирования в Jenkins:

| Файл | Описание | Расширение |
|------|---------|-----------|
| **jmeter.jtl** | Основной файл результатов | `.jtl` |
| **dashBoard_jmeter.xml** | Дэшборд JMeter | `.xml` |
| **standardResults.xml** | Стандартные результаты | `.xml` |

---

## 🔍 Как скачать файлы из Jenkins

### Шаг 1: Откройте сборку
1. Перейдите в Jenkins → выберите нужную сборку
2. Нажмите на сборку, которая вам нужна

### Шаг 2: Найдите артефакты
1. На странице сборки нажмите **"Artifacts"** (или похожую ссылку)
2. Скачайте следующие файлы:
   - `jmeter (1).jtl` → переименуйте в `jmeter.jtl`
   - `dashBoard_jmeter.xml`
   - `standardResults.xml`

### Шаг 3: Проверьте файлы
После скачивания у вас должны быть три файла в одной папке:
```
📁 Папка с файлами
├── jmeter.jtl
├── dashBoard_jmeter.xml
└── standardResults.xml
```

---

## 🚀 Запуск скрипта

### Вариант 1: Windows (PowerShell/CMD)

**Откройте Command Prompt в папке со скриптом и файлами:**

```bash
python3 convert.py jmeter.jtl dashBoard_jmeter.xml standardResults.xml report.xlsx
```

**Результат:**
- Будет создан файл `report.xlsx` в той же папке

### Вариант 2: Linux/Mac

```bash
python3 convert.py jmeter.jtl dashBoard_jmeter.xml standardResults.xml report.xlsx
```

или 

```bash
./convert.py jmeter.jtl dashBoard_jmeter.xml standardResults.xml report.xlsx
```

### Если скрипт не находится в PATH
Укажите полный путь:

```bash
python3 /path/to/convert.py jmeter.jtl dashBoard_jmeter.xml standardResults.xml report.xlsx
```

---

## 📊 Структура выходного отчета

### Лист 1: **Сводка**
- Информация о тесте (дата начала, конца, длительность)
- Таблица со всеми метриками:
  - Label (название шага)
  - # Samples (кол-во выборок)
  - Average, Median (среднее и медиана времени)
  - 90% Line, 95% Line, 99% Line (перцентили)
  - Min, Max (минимум, максимум)
  - Error % (процент ошибок)
  - Throughput (пропускная способность)
  - Received KB/sec, Sent KB/sec (скорость передачи)

### Лист 2: **График времени**
- Таблица только основных шагов (01-10)
- **Горизонтальная диаграмма** с двумя сериями:
  - Average (синие столбцы) - среднее время
  - 90% Line (оранжевые столбцы) - 90-й перцентиль

### Лист 3: **Исходные данные**
- Полные исходные данные из JTL файла

---


## ⚠️ Возможные ошибки и решения

### Ошибка: "ModuleNotFoundError: No module named 'openpyxl'"
**Решение:**
```bash
pip install openpyxl
```

### Ошибка: "No such file or directory"
**Проверьте:**
1. Все три файла находятся в одной папке со скриптом
2. Правильно написаны имена файлов
3. Вы в правильной директории:
```bash
cd C:\path\to\folder  # Windows
cd /path/to/folder    # Linux/Mac
```

### Отчет создан, но данные неправильные
**Проверьте:**
1. Что вы скачали именно эти файлы из Jenkins:
   - `jmeter.jtl` (не `jmeter (1).jtl`)
   - `dashBoard_jmeter.xml`
   - `standardResults.xml`
2. Файлы не повреждены

---

## 💡 Советы

### Автоматизация на Windows
Создайте файл `run.bat`:
```batch
@echo off
python3 convert.py jmeter.jtl dashBoard_jmeter.xml standardResults.xml report.xlsx
pause
```

Затем просто кликните на `run.bat` и скрипт запустится.

### Автоматизация на Linux/Mac
Создайте файл `run.sh`:
```bash
#!/bin/bash
python3 convert.py jmeter.jtl dashBoard_jmeter.xml standardResults.xml report.xlsx
```

Сделайте его исполняемым:
```bash
chmod +x run.sh
./run.sh
```

### Разные имена файлов
Если ваши файлы называются по-другому, просто измените команду:
```bash
python3 convert.py mytest.jtl my_dashboard.xml my_results.xml output.xlsx
```

---

## ✅ Проверка результата

После успешного выполнения вы увидите:
```
✅ Файл 'report.xlsx' успешно создан!
   Листы: Сводка, График времени, Исходные данные
   Строк данных: [количество]
```

Откройте `report.xlsx` в Excel/LibreOffice и наслаждайтесь красивым отчетом! 🎉