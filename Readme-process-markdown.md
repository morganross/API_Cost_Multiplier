process markdown interacts with gptr via the CLI. it doesnt not import functions or make api calls.

process markdown loads its variables from a config file

PM walks through the directory recursivly looking for .md files


when it finds an .md file it looks for a coresponding file in the output dir, if exists, we skip that input file for processing
for each input file WITHOUT an output file we make the file via the following process

PM reads the content of the .md file and reads the content of a specifyed instructions file and concatenates them together before sending it as a query promopt to gpt-R.

GPT-R will do work, then respond back with a  path to a final report file.

repeat this generatetion 2 more times, for 3 in totoal. conceruntly.

when we have the 3 files we then send them to eval over cli, which will retun the path to the best file via console uutput

that is the file we wrtie to the output dir, in a folder strucutre that mirrors the input's dir recursilvly