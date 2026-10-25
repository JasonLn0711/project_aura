workspace "Project AURA" "Current implementation: capture, transcription and durable evidence" {
    !include model.dsl
    views {
        !include views.dsl
        !include code-views.dsl
        styles {
            element "Element" {
                color #172b3a
                stroke #42697a
                fontSize 22
            }
            element "Person" {
                shape Person
                background #17465a
                color #ffffff
            }
            element "Software System" {
                background #17465a
                color #ffffff
            }
            element "External" {
                background #e6e9ed
                color #283642
            }
            element "Container" {
                background #d6eae7
            }
            element "Component" {
                background #edf5f3
            }
            element "Store" {
                shape Cylinder
                background #f4e9ce
            }
            element "Optional" {
                stroke #956c25
            }
            element "Retained" {
                background #eeeeee
                stroke #888888
            }
            relationship "Relationship" {
                color #42697a
                fontSize 18
                dashed false
            }
            relationship "Provisioning" {
                dashed true
                color #956c25
            }
        }
    }
    configuration {
        scope softwaresystem
    }
}
