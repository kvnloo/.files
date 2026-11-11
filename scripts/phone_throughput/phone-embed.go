// phone-embed: untimed throughput unit for the phone feeder (scripts/fleet-backfill).
//
// Starts a local llama-server in embedding mode, embeds every {"id","text"} line of
// --in, and appends {"id","n_chars","dim","f16"} lines (base64 little-endian float16,
// L2-normalised) to --out. Static Go so it runs in Android's native shell, where there
// is no python or curl on every phone. Core placement is the caller's `taskset`.
package main

import (
	"bufio"
	"bytes"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"syscall"
	"time"
)

type item struct {
	ID   string `json:"id"`
	Text string `json:"text"`
}

func f16(f float32) uint16 {
	b := math.Float32bits(f)
	sign := uint16(b>>16) & 0x8000
	exp := int((b>>23)&0xff) - 127 + 15
	man := b & 0x7fffff
	switch {
	case exp <= 0:
		return sign
	case exp >= 31:
		return sign | 0x7c00
	}
	return sign | uint16(exp<<10) | uint16(man>>13)
}

func embed(port int, texts []string) ([][]float32, error) {
	body, _ := json.Marshal(map[string]any{"input": texts, "model": "embed"})
	resp, err := http.Post(fmt.Sprintf("http://127.0.0.1:%d/v1/embeddings", port), "application/json", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("http %d: %.300s", resp.StatusCode, raw)
	}
	var out struct {
		Data []struct {
			Index     int       `json:"index"`
			Embedding []float32 `json:"embedding"`
		} `json:"data"`
	}
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, err
	}
	vecs := make([][]float32, len(texts))
	for _, d := range out.Data {
		vecs[d.Index] = d.Embedding
	}
	return vecs, nil
}

func main() {
	server := flag.String("server", "", "llama-server binary")
	model := flag.String("model", "", "embedding GGUF")
	in := flag.String("in", "", "input jsonl")
	outPath := flag.String("out", "embeddings.jsonl", "output jsonl")
	threads := flag.Int("threads", 4, "llama threads")
	port := flag.Int("port", 18431, "loopback port")
	ctx := flag.Int("ctx", 2048, "context tokens per text")
	maxChars := flag.Int("max-chars", 6000, "truncate text to this many characters")
	batch := flag.Int("batch", 4, "texts per request")
	flag.Parse()

	cmd := exec.Command(*server, "-m", *model, "--embedding", "--pooling", "last", "-t", strconv.Itoa(*threads),
		"-c", strconv.Itoa(*ctx * *batch), "-b", strconv.Itoa(*ctx), "-ub", strconv.Itoa(*ctx), "-np", strconv.Itoa(*batch),
		"--host", "127.0.0.1", "--port", strconv.Itoa(*port), "--no-webui")
	cmd.Stdout, cmd.Stderr = os.Stderr, os.Stderr
	// The llama.cpp Android bundle keeps its .so files beside the binaries.
	cmd.Env = append(os.Environ(), "LD_LIBRARY_PATH="+filepath.Dir(*server))
	// The server must die with us: adb drops the parent on disconnect and an orphaned
	// llama-server would hold ~1 GB of phone RAM forever.
	cmd.SysProcAttr = &syscall.SysProcAttr{Pdeathsig: syscall.SIGKILL}
	if err := cmd.Start(); err != nil {
		fmt.Fprintln(os.Stderr, "phone-embed: start server:", err)
		os.Exit(2)
	}
	defer cmd.Process.Kill()
	exited := make(chan error, 1)
	go func() { exited <- cmd.Wait() }()
	deadline := time.Now().Add(5 * time.Minute)
	for {
		select {
		case err := <-exited:
			fmt.Fprintln(os.Stderr, "phone-embed: server exited:", err)
			os.Exit(2)
		default:
		}
		resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/health", *port))
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == 200 {
				break
			}
		}
		if time.Now().After(deadline) {
			fmt.Fprintln(os.Stderr, "phone-embed: server never became healthy")
			os.Exit(2)
		}
		time.Sleep(time.Second)
	}

	f, err := os.Open(*in)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	out, err := os.OpenFile(*outPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	w := bufio.NewWriter(out)
	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 1<<20), 1<<24)
	var pending []item
	done, chars, t0 := 0, 0, time.Now()
	flush := func() {
		if len(pending) == 0 {
			return
		}
		texts := make([]string, len(pending))
		for i, it := range pending {
			r := []rune(it.Text)
			if len(r) > *maxChars {
				r = r[:*maxChars]
			}
			texts[i] = string(r)
		}
		vecs, err := embed(*port, texts)
		if err != nil {
			fmt.Fprintln(os.Stderr, "phone-embed:", err)
			os.Exit(1)
		}
		for i, it := range pending {
			v := vecs[i]
			var norm float64
			for _, x := range v {
				norm += float64(x) * float64(x)
			}
			norm = math.Sqrt(norm)
			buf := make([]byte, 2*len(v))
			for j, x := range v {
				binary.LittleEndian.PutUint16(buf[2*j:], f16(float32(float64(x)/norm)))
			}
			line, _ := json.Marshal(map[string]any{"id": it.ID, "n_chars": len([]rune(texts[i])), "dim": len(v),
				"f16": base64.StdEncoding.EncodeToString(buf)})
			w.Write(append(line, '\n'))
			chars += len([]rune(texts[i]))
		}
		done += len(pending)
		w.Flush()
		pending = pending[:0]
	}
	for scanner.Scan() {
		var it item
		if json.Unmarshal(scanner.Bytes(), &it) != nil || it.ID == "" {
			continue
		}
		pending = append(pending, it)
		if len(pending) >= *batch {
			flush()
		}
	}
	flush()
	w.Flush()
	out.Close()
	secs := time.Since(t0).Seconds()
	fmt.Printf("PHONE_EMBED_RESULT {\"items\":%d,\"chars\":%d,\"seconds\":%.1f}\n", done, chars, secs)
}
