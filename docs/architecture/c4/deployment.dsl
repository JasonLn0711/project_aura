deploymentEnvironment "LocalGB10" {
    deploymentNode "Linux workstation" "ARM64 GB10: validated service/inference path; device and GUI acceptance have separate gates." "Ubuntu / NVIDIA" {
        deploymentNode "Account processes" "CPU control and capture" "Python / Rust" {
            containerInstance gui
            containerInstance cli
            containerInstance capture
            containerInstance pythonCapture
            containerInstance service
            containerInstance evidence
        }
        deploymentNode "GPU execution" "Separate ASR and RE-USE environments share the physical GPU." "NVIDIA GB10 / CUDA 13" {
            containerInstance inference
            containerInstance enhancement
        }
        deploymentNode "Owner storage" "Private account data and cached models" "Filesystem" {
            containerInstance state
            containerInstance artifacts
            containerInstance spools
            containerInstance index
            containerInstance models
            containerInstance auditStore
        }
    }
}
deploymentEnvironment "SSHClient" {
    deploymentNode "CPU capture client" "Implemented topology; physical amd64/second-host acceptance remains pending." "Linux ARM64 or amd64" {
        containerInstance cli
        containerInstance capture
        containerInstance spools
        infrastructureNode "SSH forwarding" "Authenticated loopback forwarding; no publicly exposed AURA WebSocket port." "OpenSSH"
    }
    deploymentNode "NVIDIA service host" "GPU-only inference; account service owns authoritative state." "Linux / CUDA" {
        containerInstance service
        containerInstance inference
        containerInstance enhancement
        containerInstance state
        containerInstance artifacts
        containerInstance models
        containerInstance auditStore
    }
}
deploymentEnvironment "WindowsGated" {
    deploymentNode "Windows native workstation" "Packaging and diagnostic source exists. Current RE-USE environment and full hardware workflow require Windows activation; this is not a completed deployment." "Windows / NVIDIA RTX" {
        containerInstance gui
        containerInstance cli
        containerInstance pythonCapture
        containerInstance service
        containerInstance inference
        deploymentNode "RE-USE activation gate" "The current isolated runtime uses Linux-style paths; Windows RE-USE provisioning is not established." "Pending platform validation" {
            containerInstance enhancement
        }
        containerInstance state
        containerInstance artifacts
        containerInstance spools
        containerInstance models
    }
}
