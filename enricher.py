import os
import re
import yaml
import json
import traceback
from pathlib import Path
from google import genai
from google.genai.errors import APIError

# --- توابع مساعدة ---

def create_yaml_header(data):
    """إنشاء رأس YAML بتنسيق صحيح"""
    return "---\n" + yaml.dump(data, allow_unicode=True, sort_keys=False) + "---\n"

def save_ocr_review_file(doc_slug, all_corrections, output_path):
    """وظيفة جديدة لإنشاء ملف ocr_review.json - تستخدم مسار المجلد الفرعي (output_path)"""
    
    if not all_corrections:
        # print(f"  ... لم يتم العثور على أخطاء OCR محتملة. تخطي إنشاء ملف المراجعة.")
        return # لا حاجة لإنشاء ملف إذا لم تكن هناك أخطاء
        
    # تجميع ملخص للمراجعة
    total_errors = len(all_corrections)
    affected_files = len(set(c['file'] for c in all_corrections))
    
    review_data = {
        "doc": doc_slug,
        "review_summary": {
            "total_potential_errors": total_errors,
            "files_affected": affected_files
        },
        "corrections_to_review": all_corrections
    }
    
    # تحديد اسم ومسار الملف الجديد
    output_file_path = Path(output_path) / f"{doc_slug}.ocr_review.json"
    
    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(review_data, f, ensure_ascii=False, indent=2)
    
    print(f"  ✅ تم إنشاء ملف المراجعة: {output_file_path.name}")


# *******************************************************************
# دالة الاتصال بـ Gemini API 
# *******************************************************************

def call_gemini_api(article_text):
    """وظيفة الاتصال الفعلي بـ Gemini API لاستخلاص البيانات الوصفية."""
    
    system_prompt = (
        "أنت محلل قانوني خبير في معالجة نصوص القوانين والأنظمة لإنشاء بيانات وصفية (Metadata) دقيقة. "
        "مهمتك هي قراءة نص المادة المرفق وإخراج البيانات المطلوبة في صيغة JSON فقط، دون أي مقدمات أو شرح. "
        "يجب أن تكون عملية النسخ للكلمات الأصلية حرفية لغرض تصحيح الـ OCR. "
        "ركز على استخلاص المعلومات بحد أقصى للحجم (ملخص 30 كلمة، 5-8 كلمات مفتاحية)."
    )
    
    user_prompt = f"""
    بناءً على نص المادة القانونية التالي، أخرج البيانات المطلوبة بصيغة JSON:

    النص:
    ---
    {article_text}
    ---

    البيانات المطلوبة في JSON:
    {{
      "summary": "ملخص مكثف للمادة (30 كلمة كحد أقصى).",
      "keywords": ["كلمة مفتاحية 1", "كلمة مفتاحية 2", "كلمة مفتاحية 3", ...],
      "aspect": "تصنيف المادة هل هي 'إجرائي' (يشرح خطوات/إجراءات) أو 'موضوعي' (يشرح حقوق/واجبات/تعريفات).",
      "ocr_corrections": [
        {{
          "original_word": "الكلمة الأصلية الخاطئة",
          "suggested_correction": "التصحيح المقترح",
          "context": "الجملة المحيطة لتأكيد سياق الخطأ"
        }}
        # أضف كل أخطاء OCR المحتملة (مثل الهمزات، الفواصل، الأخطاء المطبعية الواضحة)
      ]
    }}
    """
    
    print("  ... جارٍ الاتصال بـ Gemini API لمعالجة البيانات...")

    if not os.getenv("GEMINI_API_KEY"):
         raise ValueError("يرجى تعيين متغير البيئة GEMINI_API_KEY قبل التشغيل.")

    try:
        client = genai.Client() 
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[user_prompt],
            config={"system_instruction": system_prompt, "response_mime_type": "application/json", "temperature": 0.0}
        )
        return json.loads(response.text.strip())
        
    except APIError as e:
        if 'permission denied' in str(e).lower() or '403' in str(e):
            raise APIError("خطأ 403: مفتاح API غير صالح أو غير مسموح به. يرجى التأكد من صلاحية المفتاح.")
        else:
            raise APIError(f"فشل الاتصال بـ Gemini API: {e}")
    except json.JSONDecodeError:
        print(f"تحذير: فشل تحليل JSON من رد الموديل. الرد الخام: {response.text}")
        return {}
    except Exception as e:
        raise Exception(f"حدث خطأ عام أثناء استدعاء API: {e}")


def load_yaml_and_content(file_path):
    """تحميل رأس YAML ومحتوى النص من ملف Markdown"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    match = re.search(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    
    if match:
        yaml_header = match.group(1)
        text_content = match.group(2)
        try:
            metadata = yaml.safe_load(yaml_header)
            return metadata, text_content
        except yaml.YAMLError as e:
            print(f"خطأ في تحليل YAML للملف {file_path}: {e}")
            return None, content
    
    return None, content

def update_alu_file(file_path, new_metadata, text_content):
    """تحديث ملف ALU بالبيانات الوصفية الجديدة"""
    
    # 1. تحديث حقول الملخص والتصحيحات
    new_metadata['summary'] = new_metadata.get('summary', 'تم تحديث الملخص بواسطة LLM.')
    new_metadata['keywords'] = new_metadata.get('keywords', [])
    new_metadata['aspect'] = new_metadata.get('aspect', 'غير مصنف')
    # في هذه المرحلة، نضمن أن يكون ocr_corrections موجوداً لغرض الـ YAML
    new_metadata['ocr_corrections'] = new_metadata.get('ocr_corrections', {})

    # 2. إعادة إنشاء رأس YAML
    updated_yaml_header = create_yaml_header(new_metadata)
    
    # 3. دمج YAML والمحتوى النصي
    final_content = updated_yaml_header + text_content.strip()
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(final_content)

# *******************************************************************
# الوظيفة الرئيسية المُحدَّثة لدعم المجلدات الفرعية
# *******************************************************************

def process_enrichment(input_folder="processed_systems_output"):
    """الوظيفة الرئيسية لتشغيل الإثراء على جميع الوثائق داخل المجلدات الفرعية."""
    
    base_path = Path(input_folder)
    
    if not base_path.exists():
        print(f"❌ لم يتم العثور على مجلد المخرجات: {input_folder}")
        return

    # 1. المرحلة الأولى: إيجاد جميع مجلدات الوثائق الفرعية
    # (نتجاهل الملفات التي قد تكون موجودة مباشرة في المجلد الرئيسي)
    doc_folders = [d for d in base_path.iterdir() if d.is_dir() and 'وثيقة-' in d.name]

    if not doc_folders:
        print(f"❌ لم يتم العثور على أي مجلدات وثائق (تبدأ بـ 'وثيقة-') في مجلد {input_folder}.")
        return

    print(f"✅ تم تجميع {len(doc_folders)} وثيقة جاهزة للإثراء.")
    
    total_processed = 0
    
    # 2. المرحلة الثانية: معالجة كل وثيقة على حدة
    for doc_folder in doc_folders:
        doc_slug = doc_folder.name
        
        print(f"\n" + "="*70)
        print(f"--- بدء الإثراء والروابط للوثيقة: {doc_slug} ---")
        
        # أ. إيجاد وترتيب جميع ملفات ALU داخل هذا المجلد الفرعي
        alu_list = []
        # البحث عن الملفات التي تبدأ بالـ slug وتنتهي برقم مادة
        alu_files = sorted(doc_folder.glob(f"{doc_slug}*--مادة-*.md")) 

        for file_path in alu_files:
            metadata, _ = load_yaml_and_content(file_path)
            if not metadata: continue

            # استخراج رقم المادة للترتيب
            article_range_match = re.search(r'--مادة-(\d+)', metadata.get('id', ''))
            sort_key = int(article_range_match.group(1)) if article_range_match else 0
            
            alu_list.append({'id': metadata.get('id'), 'path': file_path, 'sort_key': sort_key})

        alu_list.sort(key=lambda x: x['sort_key'])

        if not alu_list:
            print(f"  ❌ لم يتم العثور على أي ملفات ALU (مادة) صالحة للوثيقة {doc_slug}. تخطي.")
            continue

        print(f"  > تم العثور على {len(alu_list)} مادة جاهزة للمعالجة.")
        
        # ب. معالجة الإثراء (الروابط و LLM)
        all_doc_ocr_corrections = [] 
        
        for i, alu_data in enumerate(alu_list):
            current_path = alu_data['path']
            
            # تحديد السابق والتالي باستخدام قائمة ALU المرتبة
            prev_id = alu_list[i-1]['id'] if i > 0 else None
            next_id = alu_list[i+1]['id'] if i < len(alu_list) - 1 else None
            
            metadata, text_content = load_yaml_and_content(current_path)
            
            if metadata:
                # تحديث الروابط
                metadata['prev'] = prev_id
                metadata['next'] = next_id
                
                article_text_for_llm = text_content.strip()
                
                try:
                    llm_data = call_gemini_api(article_text_for_llm)
                    
                    # دمج بيانات LLM في الميتاداتا
                    metadata['summary'] = llm_data.get('summary', metadata.get('summary'))
                    metadata['keywords'] = llm_data.get('keywords', metadata.get('keywords', []))
                    metadata['aspect'] = llm_data.get('aspect', metadata.get('aspect', 'غير مصنف'))
                    
                    llm_corrections = llm_data.get('ocr_corrections', [])
                    
                    # 1. تحديث ocr_corrections في رأس YAML
                    metadata['ocr_corrections'] = {c['original_word']: c['suggested_correction'] for c in llm_corrections if 'original_word' in c and 'suggested_correction' in c}
                    
                    # 2. تجميع البيانات لملف ocr_review.json
                    article_number = metadata.get('articles', metadata.get('id').split('--مادة-')[-1])
                    for correction in llm_corrections:
                        correction_record = correction.copy()
                        correction_record['file'] = current_path.name
                        correction_record['article_number'] = article_number
                        all_doc_ocr_corrections.append(correction_record)


                    # تحديث الملف بالكامل
                    update_alu_file(current_path, metadata, text_content)
                    print(f"  ✅ تم تحديث وإثراء الملف: {current_path.name}")
                    total_processed += 1
                
                except Exception as e:
                    print(f"  ❌ فشل إثراء الملف {current_path.name}. الخطأ: {e}")
                    # استمرار التحديث بالروابط حتى لو فشل LLM (للحفاظ على الروابط)
                    update_alu_file(current_path, metadata, text_content)
                    total_processed += 1

        # ج. حفظ ملف ocr_review.json بعد معالجة جميع المواد
        save_ocr_review_file(doc_slug, all_doc_ocr_corrections, doc_folder) # <--- تمرير مسار المجلد الفرعي

    print("\n" + "="*70)
    print(f"✅ اكتمل الإثراء الدفعي. تم تحديث {total_processed} ملف ALU في {len(doc_folders)} وثيقة.")
    print("==========================================================")

# --- التشغيل المُحسَّن ---
if __name__ == "__main__":
    print("✅ تم تحميل الكود بنجاح. بدء المعالجة الدفعية...")
    
    try:
        process_enrichment()
    except Exception as e:
        print("\n" + "="*70)
        print("--- خطأ فادح غير متوقع أثناء تشغيل المعالج ---")
        print(f"❌ تعثر السكربت عند هذه النقطة: {e}")
        print("="*70)
        traceback.print_exc()