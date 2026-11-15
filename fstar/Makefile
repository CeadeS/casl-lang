# CASL — F* verification (run on a machine with fstar.exe on PATH; Z3 ships with F*)
#
#   make verify     # type-check + SMT-verify CASL.fst  (expect RC=0, 0 admits)
#   make extract    # extract the verified core to OCaml (engine; Rust via Pulse/KaRaMeL later)
#   make tcb-bridge # H1 step: extracted F* kernel vs. Python checker on an exhaustive corpus
#   make clean

FSTAR ?= fstar.exe

.PHONY: verify extract ocaml-run tcb-bridge clean
verify:
	$(FSTAR) CASL.fst
	$(FSTAR) Forwarding.fst    # CERT-FID — forwarding fidelity (A1), standalone companion module

extract:
	mkdir -p out
	$(FSTAR) --codegen OCaml --odir out --extract CASL CASL.fst

# extract the verified core into the dune project and run the driver
ocaml-run:
	$(FSTAR) --codegen OCaml --odir ocaml --extract CASL CASL.fst
	cd ocaml && dune exec ./driver.exe

# TCB differential bridge (H1 / LH-C-004): regenerate the single-sourced corpus + driver,
# re-extract the verified core, and compare its projectability verdicts with the Python
# checker (offline). Corpus is single-sourced from src/casl/tcb_corpus.py.
tcb-bridge:
	cd .. && PYTHONPATH=src python3 src/casl/tcb_corpus.py
	$(FSTAR) --codegen OCaml --odir ocaml --extract CASL CASL.fst
	cd .. && PYTHONPATH=src python3 src/casl/tcb_bridge.py

clean:
	rm -rf out *.checked ocaml/CASL.ml ocaml/_build
