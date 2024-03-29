/*-
 * Copyright (c) 2014 Red Hat, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.fedoraproject.copr.client.impl;

import java.util.Collections;
import java.util.List;

import org.fedoraproject.copr.client.BuildResult;

/**
 * @author Mikolaj Izdebski
 */
public class DefaultBuildResult
    implements BuildResult
{
    private final List<Long> buildIds;

    private final String message;

    public DefaultBuildResult( List<Long> buildIds, String message )
    {
        this.buildIds = buildIds;
        this.message = message;
    }

    @Override
    public List<Long> getBuildIds()
    {
        return Collections.unmodifiableList( buildIds );
    }

    @Override
    public String getMessage()
    {
        return message;
    }
}
