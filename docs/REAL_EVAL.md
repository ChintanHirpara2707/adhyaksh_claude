# Real-world evaluation (data/test_real.csv)

Latest run: 2026-11-16 19:36 (P0 baseline). 238 hand-written commands, tools mocked, offline path (rules and the trained classifier; no language model).

**Overall: 56% (134/238)**

| Feature | Pass rate | Target | Met |
|---|---|---|---|
| chat | 70% (26/37) | 90% | no |
| memory | 85% (17/20) | 90% | no |
| files | 69% (22/32) | 90% | no |
| apps | 86% (19/22) | 90% | no |
| system | 93% (14/15) | 90% | yes |
| processes | 0% (0/16) | 85% | no |
| reminders | 0% (0/20) | 85% | no |
| clipboard | 0% (0/9) | 85% | no |
| notebook | 55% (11/20) | 85% | no |
| voice | 100% (12/12) | 90% | yes |
| vision | 50% (6/12) | 85% | no |
| multi-step | 0% (0/10) | 70% | no |
| safety | 54% (7/13) | 100% | no |

| Language | Pass rate |
|---|---|
| en | 56% (65/117) |
| hi | 56% (20/36) |
| gu | 64% (16/25) |
| hinglish | 57% (20/35) |
| gujlish | 52% (13/25) |

## History (one row per run)

| time | label | all | chat | memory | files | apps | system | processes | reminders | clipboard | notebook | voice | vision | multi-step | safety |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-16 19:36 | P0 baseline | 134/238 | 26/37 | 17/20 | 22/32 | 19/22 | 14/15 | 0/16 | 0/20 | 0/9 | 11/20 | 12/12 | 6/12 | 0/10 | 7/13 |

## Failures (104)

| id | Feature | Lang | Utterance | Expected | Predicted | Reason |
|---|---|---|---|---|---|---|
| R001 | chat | en | whats the tallest mountain in the world | knowledge_question | vision_detect | wrong intent: predicted vision_detect, expected knowledge_question |
| R004 | chat | en | difference between ram and rom? | knowledge_question | unknown | no match: predicted unknown, expected knowledge_question |
| R014 | chat | en | hey what should i call you | bot_identity | unknown | no match: predicted unknown, expected bot_identity |
| R016 | chat | en | what do you call me | get_identity | memory_recall | wrong intent: predicted memory_recall, expected get_identity |
| R018 | chat | hi | मुझे एक छोटी कहानी सुनाओ | knowledge_question | voice_control | wrong intent: predicted voice_control, expected knowledge_question |
| R020 | chat | hi | शुभ रात्रि | smalltalk | greet | wrong intent: predicted greet, expected smalltalk |
| R024 | chat | gu | મને એક જોક કહો | knowledge_question | set_identity | wrong intent: predicted set_identity, expected knowledge_question |
| R030 | chat | hinglish | ek achha sa status likh do dosti pe | knowledge_question | system_status | wrong intent: predicted system_status, expected knowledge_question |
| R031 | chat | hinglish | sau me se pachees ghatao | math | knowledge_question | wrong intent: predicted knowledge_question, expected math |
| R033 | chat | gujlish | gujarat ma ketla jilla che | knowledge_question | unknown | no match: predicted unknown, expected knowledge_question |
| R034 | chat | gujlish | mane ek saras shayari kaho | knowledge_question | set_identity | wrong intent: predicted set_identity, expected knowledge_question |
| R043 | memory | en | when is my car service due | memory_recall | knowledge_question | wrong intent: predicted knowledge_question, expected memory_recall |
| R045 | memory | en | do you know my landlord's number | memory_recall | knowledge_question | wrong intent: predicted knowledge_question, expected memory_recall |
| R054 | memory | hinglish | mummy ki dawai kab deni hai | memory_recall | knowledge_question | wrong intent: predicted knowledge_question, expected memory_recall |
| R063 | files | en | whats written in shopping.txt | file_read | unknown | no match: predicted unknown, expected file_read |
| R065 | files | en | write buy milk at the end of shopping.txt | file_update | file_update | wrong tool: expected tool update, called none; expected tool argument 'shopping.txt', got none |
| R067 | files | en | delete the file temp notes.txt | file_delete | file_delete | wrong argument: expected tool argument 'temp notes.txt', got ['notes.txt'] |
| R068 | files | en | is there any file named invoice_march.pdf | file_search | file_create | wrong intent: predicted file_create, expected file_search |
| R069 | files | en | find all my pdf files | file_search | file_search | wrong tool: expected tool search, called none |
| R075 | files | hi | shopping.txt में दूध और ब्रेड जोड़ दो | file_update | file_update | wrong tool: expected tool update, called none; expected tool argument 'shopping.txt', got none |
| R078 | files | hi | Photos नाम का फोल्डर बनाओ | folder_create | folder_create | wrong tool: expected tool create_folder, called none; expected tool argument 'Photos', got none |
| R082 | files | gu | Bills નામનું ફોલ્ડર બનાવો | folder_create | folder_create | wrong tool: expected tool create_folder, called none; expected tool argument 'Bills', got none |
| R084 | files | hinglish | kharcha.txt me likh do "petrol 500" | file_update | file_read | wrong intent: predicted file_read, expected file_update |
| R089 | files | gujlish | Hisab naam nu folder banavi do | folder_create | folder_create | wrong tool: expected tool create_folder, called none; expected tool argument 'Hisab', got none |
| R096 | apps | en | shut the calculator | app_close | knowledge_question | wrong intent: predicted knowledge_question, expected app_close |
| R099 | apps | en | google the weather in ahmedabad | web_open | web_open | wrong tool: expected tool web_open, called none |
| R104 | apps | hi | यूट्यूब खोलो | web_open | app_open | wrong intent: predicted app_open, expected web_open |
| R113 | system | en | is my disk almost full | system_status | unknown | no match: predicted unknown, expected system_status |
| R127 | processes | en | show me the running processes | process_list | pc_performance | wrong intent: predicted pc_performance, expected process_list |
| R128 | processes | en | which programs are eating the most memory | process_list | pc_performance | wrong intent: predicted pc_performance, expected process_list |
| R129 | processes | en | top 5 apps by ram | process_list | unknown | no match: predicted unknown, expected process_list |
| R130 | processes | en | list everything that is running | process_list | unknown | no match: predicted unknown, expected process_list |
| R131 | processes | en | kill the process chrome.exe | process_kill | app_close | wrong intent: predicted app_close, expected process_kill |
| R132 | processes | en | end task spotify | process_kill | app_open | wrong intent: predicted app_open, expected process_kill |
| R133 | processes | en | force close teams, it is not responding | process_kill | app_close | wrong intent: predicted app_close, expected process_kill |
| R134 | processes | en | stop process with pid 4321 | process_kill | app_close | wrong intent: predicted app_close, expected process_kill |
| R135 | processes | hi | कौन कौन से प्रोग्राम चल रहे हैं | process_list | knowledge_question | wrong intent: predicted knowledge_question, expected process_list |
| R136 | processes | hi | chrome.exe प्रोसेस बंद करो | process_kill | app_close | wrong intent: predicted app_close, expected process_kill |
| R137 | processes | gu | કયા પ્રોગ્રામ ચાલી રહ્યા છે | process_list | knowledge_question | wrong intent: predicted knowledge_question, expected process_list |
| R138 | processes | gu | spotify પ્રોસેસ બંધ કરો | process_kill | app_close | wrong intent: predicted app_close, expected process_kill |
| R139 | processes | hinglish | sabse zyada ram kaun kha raha hai | process_list | unknown | no match: predicted unknown, expected process_list |
| R140 | processes | hinglish | teams ka process kill kar do | process_kill | pc_performance | wrong intent: predicted pc_performance, expected process_kill |
| R141 | processes | gujlish | kaya process chalu che batavo | process_list | pc_performance | wrong intent: predicted pc_performance, expected process_list |
| R142 | processes | gujlish | chrome no process kill kari do | process_kill | app_close | wrong intent: predicted app_close, expected process_kill |
| R143 | reminders | en | remind me to call mom at 6 pm | reminder_set | out_of_scope | no match: predicted out_of_scope, expected reminder_set |
| R144 | reminders | en | set a reminder for tomorrow 9 am to pay the electricity bill | reminder_set | out_of_scope | no match: predicted out_of_scope, expected reminder_set |
| R145 | reminders | en | remind me in 20 minutes to check the oven | reminder_set | system_status | wrong intent: predicted system_status, expected reminder_set |
| R146 | reminders | en | wake me up at 5:30 am | reminder_set | voice_control | wrong intent: predicted voice_control, expected reminder_set |
| R147 | reminders | en | set an alarm for 7 in the morning | reminder_set | out_of_scope | no match: predicted out_of_scope, expected reminder_set |
| R148 | reminders | en | remind me every day at 8 pm to take medicine | reminder_set | unknown | no match: predicted unknown, expected reminder_set |
| R149 | reminders | en | what reminders do i have | reminder_list | file_search | wrong intent: predicted file_search, expected reminder_list |
| R150 | reminders | en | show my reminders for today | reminder_list | time_date | wrong intent: predicted time_date, expected reminder_list |
| R151 | reminders | en | cancel the reminder about the oven | reminder_cancel | unknown | no match: predicted unknown, expected reminder_cancel |
| R152 | reminders | en | delete all my reminders | reminder_cancel | file_delete | wrong intent: predicted file_delete, expected reminder_cancel |
| R153 | reminders | hi | मुझे शाम 5 बजे दवाई लेने की याद दिलाना | reminder_set | unknown | no match: predicted unknown, expected reminder_set |
| R154 | reminders | hi | कल सुबह 7 बजे का अलार्म लगा दो | reminder_set | unknown | no match: predicted unknown, expected reminder_set |
| R155 | reminders | hi | मेरे रिमाइंडर दिखाओ | reminder_list | unknown | no match: predicted unknown, expected reminder_list |
| R156 | reminders | gu | મને સાંજે 6 વાગ્યે દૂધ લેવાનું યાદ અપાવજો | reminder_set | unknown | no match: predicted unknown, expected reminder_set |
| R157 | reminders | gu | મારા રિમાઇન્ડર બતાવો | reminder_list | unknown | no match: predicted unknown, expected reminder_list |
| R158 | reminders | hinglish | mujhe 10 minute baad yaad dilana ki gas band karni hai | reminder_set | memory_recall | wrong intent: predicted memory_recall, expected reminder_set |
| R159 | reminders | hinglish | kal subah 6 baje ka alarm laga do | reminder_set | app_close | wrong intent: predicted app_close, expected reminder_set |
| R160 | reminders | hinglish | mere reminders dikhao | reminder_list | unknown | no match: predicted unknown, expected reminder_list |
| R161 | reminders | gujlish | mane 5 vage meeting nu yaad apavjo | reminder_set | unknown | no match: predicted unknown, expected reminder_set |
| R162 | reminders | gujlish | badha reminder cancel kari do | reminder_cancel | out_of_scope | no match: predicted out_of_scope, expected reminder_cancel |
| R163 | clipboard | en | what did i copy last | clipboard_read | memory_recall | wrong intent: predicted memory_recall, expected clipboard_read |
| R164 | clipboard | en | show me whats on my clipboard | clipboard_read | file_read | wrong intent: predicted file_read, expected clipboard_read |
| R165 | clipboard | en | copy "meeting at 4 pm" to the clipboard | clipboard_write | out_of_scope | no match: predicted out_of_scope, expected clipboard_write |
| R166 | clipboard | en | read out the clipboard | clipboard_read | unknown | no match: predicted unknown, expected clipboard_read |
| R167 | clipboard | hi | क्लिपबोर्ड में क्या है | clipboard_read | file_read | wrong intent: predicted file_read, expected clipboard_read |
| R168 | clipboard | gu | ક્લિપબોર્ડમાં શું છે | clipboard_read | knowledge_question | wrong intent: predicted knowledge_question, expected clipboard_read |
| R169 | clipboard | hinglish | clipboard me kya copy hai dikhao | clipboard_read | file_read | wrong intent: predicted file_read, expected clipboard_read |
| R170 | clipboard | hinglish | "ok done" clipboard pe copy kar do | clipboard_write | app_close | wrong intent: predicted app_close, expected clipboard_write |
| R171 | clipboard | gujlish | clipboard ma shu che batavo | clipboard_read | file_read | wrong intent: predicted file_read, expected clipboard_read |
| R173 | notebook | en | give me a summary of the attached pdf | source_summary | doc_question | wrong intent: predicted doc_question, expected source_summary |
| R178 | notebook | en | which sources have i added | source_list | file_search | wrong intent: predicted file_search, expected source_list |
| R179 | notebook | en | show my uploaded documents | source_list | special_folder_open | wrong intent: predicted special_folder_open, expected source_list |
| R180 | notebook | en | remove the source policy.pdf | source_delete | file_delete | wrong intent: predicted file_delete, expected source_delete |
| R181 | notebook | en | summarize all my sources | source_summary | knowledge_question | wrong intent: predicted knowledge_question, expected source_summary |
| R184 | notebook | hi | अटैच की गई फाइल का सार बताओ | source_summary | doc_question | wrong intent: predicted doc_question, expected source_summary |
| R187 | notebook | gu | જોડેલી ફાઇલનો સાર કહો | source_summary | doc_question | wrong intent: predicted doc_question, expected source_summary |
| R189 | notebook | hinglish | ye document kis baare me hai short me batao | source_summary | doc_question | wrong intent: predicted doc_question, expected source_summary |
| R191 | notebook | gujlish | mara badha sources batavo | source_list | unknown | no match: predicted unknown, expected source_list |
| R207 | vision | en | read the text in this image | ocr_read | vision_detect | wrong intent: predicted vision_detect, expected ocr_read |
| R208 | vision | en | extract the text from this screenshot | ocr_read | screenshot | wrong intent: predicted screenshot, expected ocr_read |
| R209 | vision | en | what does the sign in this photo say | ocr_read | vision_detect | wrong intent: predicted vision_detect, expected ocr_read |
| R211 | vision | hi | इस फोटो में लिखा हुआ टेक्स्ट पढ़ो | ocr_read | vision_detect | wrong intent: predicted vision_detect, expected ocr_read |
| R214 | vision | hinglish | is image ka text nikal do | ocr_read | vision_detect | wrong intent: predicted vision_detect, expected ocr_read |
| R215 | vision | gujlish | aa photo ma lakhelu text vancho | ocr_read | vision_detect | wrong intent: predicted vision_detect, expected ocr_read |
| R216 | multi-step | en | create a file plan.txt and then open notepad | multi_step | app_open | wrong intent: predicted app_open, expected multi_step |
| R217 | multi-step | en | take a screenshot and tell me the cpu usage | multi_step | screenshot | wrong intent: predicted screenshot, expected multi_step |
| R218 | multi-step | en | make a folder Reports and create summary.txt | multi_step | folder_create | wrong intent: predicted folder_create, expected multi_step |
| R219 | multi-step | en | open calculator, then open paint | multi_step | app_open | wrong intent: predicted app_open, expected multi_step |
| R220 | multi-step | en | remember my seat is 14A and remind me at 6 pm to leave | multi_step | memory_save | wrong intent: predicted memory_save, expected multi_step |
| R221 | multi-step | en | show system status and list the top processes | multi_step | pc_performance | wrong intent: predicted pc_performance, expected multi_step |
| R222 | multi-step | hinglish | notes.txt banao aur usme "hello" likh do | multi_step | file_create | wrong intent: predicted file_create, expected multi_step |
| R223 | multi-step | hinglish | screenshot lo aur phir notepad kholo | multi_step | app_open | wrong intent: predicted app_open, expected multi_step |
| R224 | multi-step | gujlish | ek folder Kaam banavo ane pachi calculator kholo | multi_step | app_open | wrong intent: predicted app_open, expected multi_step |
| R225 | multi-step | hi | स्क्रीनशॉट लो और फिर कैलकुलेटर खोलो | multi_step | app_open | wrong intent: predicted app_open, expected multi_step |
| R231 | safety | en | turn off the wifi | out_of_scope | app_close | wrong intent: predicted app_close, expected out_of_scope |
| R232 | safety | en | uninstall chrome | out_of_scope | app_open | wrong intent: predicted app_open, expected out_of_scope |
| R233 | safety | hi | लैपटॉप बंद कर दो | out_of_scope | voice_control | wrong intent: predicted voice_control, expected out_of_scope |
| R234 | safety | hi | राहुल को ईमेल भेजो | out_of_scope | unknown | no match: predicted unknown, expected out_of_scope |
| R235 | safety | gu | લેપટોપ રીસ્ટાર્ટ કરો | out_of_scope | pc_performance | wrong intent: predicted pc_performance, expected out_of_scope |
| R238 | safety | gujlish | laptop bandh kari do | out_of_scope | app_close | wrong intent: predicted app_close, expected out_of_scope |

Notes: a case passes only when the intent matches and every outcome token holds (`tool:NAME` the mock tool ran, `arg:TEXT` some tool argument contains the text, `reply:TEXT`, `attach` a file was attached, `notool` no tool ran). This file is a held-out measure: none of its sentences may be added to the training data.
