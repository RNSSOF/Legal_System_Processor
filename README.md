# منصة الإعداد الآلي للأنظمة القانونية (Legal System Preparation Pipeline)

هذا المشروع يوفر سكريبتات Python لإعداد وتجهيز ملفات القوانين والأنظمة (بصيغة Markdown) للمعالجة الآلية والإثراء بالذكاء الاصطناعي (باستخدام Google Gemini).

---

## الميزات الرئيسية

1.  **التقسيم الدفعي (Batch Splitting):** تقسيم آلي للملفات إلى وحدات ذرية قانونية (ALUs) لكل مادة.
2.  **التنظيم الهيكلي:** إنشاء مجلدات فرعية لكل وثيقة لضمان النظام والسهولة في التعامل مع الآلاف من الوثائق.
3.  **الإثراء الذكي (LLM Enrichment):** إضافة بيانات وصفية غنية (ملخصات، كلمات مفتاحية، تصنيفات).
4.  **الترابط الآلي:** ربط المواد ببعضها البعض (المادة السابقة والتالية) لتسهيل التنقل السياقي.

---

## الإعداد والتشغيل

### المتطلبات الأساسية

* Python 3.8+
* مفتاح [Gemini API Key](https://ai.google.dev/gemini-api/docs/api-key) (مطلوب فقط لمرحلة الإثراء).

### خطوات التثبيت

1.  **تثبيت المكتبات:**
    ```bash
    pip install -r requirements.txt
    ```
2.  **إعداد مفتاح API:** يجب تعيين مفتاح Gemini API كمتغير بيئة.

    * **لأنظمة التشغيل Windows (PowerShell أو Git Bash):**
        ```bash
        export GEMINI_API_KEY="YOUR_API_KEY_HERE"
        # أو استخدم الأمر الخاص بـ PowerShell:
        # $env:GEMINI_API_KEY="YOUR_API_KEY_HERE"
        ```

### هيكلة المشروع

يجب وضع الملفات القانونية الأصلية داخل مجلد **`source_files`**.

Legal_Splitter/ ├── source_files/ ├── processed_systems_output/ ├── splitter.py ├── enricher.py └── requirements.txt


---

## سير العمل (Workflow)

يتم تنفيذ النظام على خطوتين متتاليتين:

### المرحلة الأولى: التقسيم والتنظيم (`splitter.py`)

**الغرض:** تقسيم الملفات وتجهيزها هيكلياً دون الاتصال بـ Gemini.

```bash
python splitter.py
المرحلة الثانية: الإثراء والربط (enricher.py)
الغرض: استدعاء Gemini API لإضافة البيانات الوصفية، الروابط، وتحديد أخطاء OCR.

Bash

python enricher.py
النتيجة النهائية: ستجد جميع الوثائق الجاهزة للمخزن في مجلد processed_systems_output، منظمة في مجلدات فرعية خاصة بكل وثيقة.
