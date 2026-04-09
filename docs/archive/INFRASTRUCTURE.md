# SST Infrastructure

---

## 1. Node Definitions

### SST-Scout-VM

* Ubuntu Desktop
* Docker
* browser-use

---

### SST-Core-VM

* Ubuntu Server
* Docker
* Prefect
* SeaweedFS S3 gateway

---

### SST-Worker-CT

* Ubuntu Server container
* Mounted storage:

  * /mnt/work_area (USB-SSD)

---

### M2 Mac

* Ollama
* Local LLM inference

---

## 2. Storage

* SeaweedFS S3-compatible storage
* Versioning enabled

---

## 3. Processing Tools

* FFmpeg
* Mutagen

---

## 4. Network

* Local network (shub-niggurath)
* Shared storage access

---

## 5. Execution Flow

Scout → Core → Worker → Storage

---

## 6. Scaling Strategy

* Add Worker containers
* Scale Prefect workers

---

## 7. Fault Tolerance

* Prefect retry
* SeaweedFS object versioning

---

# END
