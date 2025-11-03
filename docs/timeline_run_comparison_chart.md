# Timeline Run Comparison Chart (Last Run Window)

Window analyzed: 2025-11-02 16:31:45 .. 16:40:56 (from acm_session.log)  
External outputs directory:  
C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs

Column 3 lists only files whose LastWriteTime falls within the window above.

| Expected (from config)                         | Timeline reported (16:40:53 block)                 | Files created in external outputs during the window |
|-----------------------------------------------|----------------------------------------------------|-----------------------------------------------------|
| fpf • openai • gpt-5-mini                     | — missing                                          | —                                                   |
| fpf • openai • gpt-5-nano                     | FPF rest, gpt-5-nano                               | —                                                   |
| fpf • openai • o4-mini                        | FPF rest, o4-mini                                  | —                                                   |
| fpf • openaidp • o4-mini-deep-research        | FPF deep, o4-mini-deep-research                    | —                                                   |
| gptr • openai • gpt-4.1-nano                  | GPT-R standard, openai:gpt-4.1-nano                | 100_ EO 14er & Block.gptr.1.gpt-4.1-nano.cgl.md     |
| gptr • openai • gpt-5-mini                    | GPT-R standard, openai:gpt-5-mini                  | 100_ EO 14er & Block.gptr.1.gpt-5-mini.dmq.md       |
| dr • google_genai • gemini-2.5-flash-lite     | GPT-R deep, google_genai:gemini-2.5-flash-lite     | 100_ EO 14er & Block.dr.1.gemini-2.5-flash-lite.m8n.md |
| ma • gpt-4.1-nano                             | MA, gpt-4.1-nano (3 entries)                       | 100_ EO 14er & Block.ma.1.gpt-4.1-nano.q0v.md; 100_ EO 14er & Block.ma.2.gpt-4.1-nano.qmj.docx; 100_ EO 14er & Block.ma.3.gpt-4.1-nano.rrm.md |

Where are the FPF files?  
They are present in the outputs directory (e.g., “100_ EO 14er & Block.fpf.3.gpt-5-mini.3ic.txt”, “...fpf.2.gpt-5-nano.99h.txt”, “...fpf.1.o4-mini.wjt.txt”, “...o4-mini-deep-research.fpf-1-1.fpf.response.txt”), but their LastWriteTime falls outside the last-run window above, so column 3 shows “—”. The evaluator (EVAL_BEST/EVAL_EXPORTS) selected/used FPF content around 16:40:53, which did not entail new writes to the external outputs directory at that exact time.
