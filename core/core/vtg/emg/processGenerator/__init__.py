from core.vtg.emg.processGenerator import linuxInsmod, linuxModule, manualImporter


def generate_processes(logger, conf, source, avt):
    raise NotImplementedError

    # Get instance maps if possible
    instance_maps = dict()
    extra_processes = dict()
    if get_conf_property(self.conf, "EMG instances"):
        self.logger.info('Looking for a file with an instance map {!r}'.
                         format(get_necessary_conf_property(self.conf, "EMG instances")))
        with open(core.utils.find_file_or_dir(self.logger,
                                              get_necessary_conf_property(self.conf, "main working directory"),
                                              get_necessary_conf_property(self.conf, "EMG instances")),
                  encoding='utf8') as fp:
            instance_maps = json.load(fp)
    if get_conf_property(self.conf, "extra processes"):
        self.logger.info('Looking for a file with additional processes {!r}'.
                         format(get_necessary_conf_property(self.conf, "extra processes")))
        with open(core.utils.find_file_or_dir(self.logger,
                                              get_necessary_conf_property(self.conf, "main working directory"),
                                              get_necessary_conf_property(self.conf, "extra processes")),
                  encoding='utf8') as fp:
            extra_processes = json.load(fp)

    model = ProcessModel(self.logger, get_necessary_conf_property(self.conf, 'intermediate model options'),
                         model_processes, env_processes,
                         self.__get_json_content(get_necessary_conf_property(self.conf,
                                                                             'intermediate model options'),
                                                 "roles map file"))
    instance_maps, generated_processes = model.prepare_event_model(ics, instance_maps)
    # Send data to the server
    self.logger.info("Send data on generated instances to server")
    core.utils.report(self.logger,
                      'data',
                      {
                          'id': self.id,
                          'data': instance_maps
                      },
                      self.mqs['report files'],
                      self.vals['report id'],
                      get_necessary_conf_property(self.conf, "main working directory"))
    self.logger.info("An intermediate environment model has been prepared")

    # Merge manually prepared processes with generated ones and provide the model to modelTranslator
    # todo: how to replace main process
    if extra_processes:
        for category in extra_processes:
            generated_processes[category].update(extra_processes[category])

    # Parse this final model
    model_processes, env_processes, entry_process = \
        parse_event_specification(self.logger,
                                  get_necessary_conf_property(self.conf, 'intermediate model options'),
                                  generated_processes, abstract=False)
    # replace processes
    model.entry_process = entry_process
    model.event_processes = list(env_processes.values())
    model.model_processes = list(model_processes.values())

    # Generate module interface specification
    self.logger.info("============== An intermediat model translation stage ==============")
    check_or_set_conf_property(self.conf, 'translation options', default_value=dict(), expected_type=dict)

    # Dump to disk instance map
    instance_map_file = 'instance map.json'
    self.logger.info("Dump information on chosen instances to file '{}'".format(instance_map_file))
    with open(instance_map_file, "w", encoding="utf8") as fh:
        fh.writelines(json.dumps(instance_maps, ensure_ascii=False, sort_keys=True, indent=4))

    # Find specifications
    self.logger.info("Determine which specifications are provided")
    interface_spec, event_categories_spec = self.__get_specs(self.logger, spec_dir)
    self.logger.info("All necessary data has been successfully found")


def __merge_spec_versions(self, collection, user_tag):
    # Copy data to a final spec
    def import_specification(spec, final_spec):
        for tag in spec:
            if tag not in final_spec:
                final_spec[tag] = spec[tag]
            else:
                for new_tag in spec[tag]:
                    if new_tag in final_spec[tag]:
                        raise KeyError("Do not expect dublication of entry '{}' in '{}' while composing a final EMG"
                                       " specification".format(new_tag, tag))
                    final_spec[tag][new_tag] = spec[tag][new_tag]

    def match_default_tag(entry):
        dt = re.compile('\(base\)')

        for tag in entry:
            if dt.search(tag):
                return tag

        return None

    final_specification = dict()

    # Import each entry
    for entry in collection:
        if user_tag in entry:
            # Find provided by a user tag
            import_specification(entry[user_tag], final_specification)
        else:
            # Search for a default tag
            dt = match_default_tag(entry)
            if dt:
                import_specification(entry[dt], final_specification)

    # Return final specification
    return final_specification


def __save_collection(self, logger, collection, file):
    logger.info("Print final merged specification to '{}'".format(file))
    with open(file, "w", encoding="utf8") as fh:
        json.dump(collection, fh, ensure_ascii=False, sort_keys=True, indent=4)

